from core.config_loader import ConfigLoader
from core.config_validator import ConfigValidator
from core.logger import LogLevel, Logger


def make_fake_cmds(plugin_loaded=False, plugin_error=None,
                   attr_exists=True, node_create_error=None):
    class FakeCmds:
        def __init__(self):
            self.calls = []
            self.plugin_loaded = plugin_loaded
            self.plugin_error = plugin_error
            self.attr_exists = attr_exists
            self.node_create_error = node_create_error

        def pluginInfo(self, plugin, query=True, loaded=True):
            self.calls.append(("pluginInfo", plugin))
            return self.plugin_loaded

        def loadPlugin(self, plugin):
            self.calls.append(("loadPlugin", plugin))
            if self.plugin_error is not None:
                raise self.plugin_error

        def shadingNode(self, node_type, **kwargs):
            self.calls.append(("shadingNode", node_type))
            if self.node_create_error is not None:
                raise self.node_create_error
            return f"tmp_{node_type}"

        def attributeQuery(self, attr, node=None, exists=True):
            self.calls.append(("attributeQuery", attr, node))
            return self.attr_exists

        def objExists(self, node):
            self.calls.append(("objExists", node))
            return True

        def delete(self, node):
            self.calls.append(("delete", node))

    return FakeCmds()


def test_plugin_failure_skips_without_errors():
    """未安装渲染器必须整组 SKIP，绝不产生 ERROR/WARN。"""
    fake = make_fake_cmds(plugin_error=RuntimeError("plugin not installed"))
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    results, summary = validator.validate_all()
    assert summary["error"] == 0
    assert summary["warn"] == 0
    # 三个插件（mtoa / redshift4maya / vrayformaya）各产生至少一条 SKIP
    assert summary["skip"] >= 3
    assert all(r.level != LogLevel.ERROR and r.level != LogLevel.WARN for r in results)


def test_plugin_loaded_emits_info():
    fake = make_fake_cmds(plugin_loaded=True)
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    validator._check_plugin("mtoa", "scope")
    levels = [r.level for r in validator._results]
    assert LogLevel.INFO in levels
    assert any("loaded" in r.detail for r in validator._results)


def test_create_temp_failure_emits_error():
    fake = make_fake_cmds(node_create_error=RuntimeError("unknown node type"))
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    node = validator._create_temp("Nope", "shader", "scope")
    assert node is None
    errors = [r for r in validator._results if r.level == LogLevel.ERROR]
    assert len(errors) == 1
    assert "could not be created" in errors[0].detail


def test_check_attr_ok_and_not_found():
    fake = make_fake_cmds(attr_exists=True)
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    validator._check_attr("n1", "T1", "attrA", "s", "descA")
    fake.attr_exists = False
    validator._check_attr("n1", "T1", "attrB", "s", "descB")
    levels = [r.level for r in validator._results]
    assert levels == [LogLevel.OK, LogLevel.ERROR]
    assert "NOT FOUND" in validator._results[1].detail


def test_validate_all_summary_and_cleanup():
    fake = make_fake_cmds(plugin_loaded=True)
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    results, summary = validator.validate_all()
    assert summary["ok"] > 0
    assert summary["error"] == 0
    assert summary["total"] == len(results)
    assert summary["total"] == sum(
        summary[k] for k in ("ok", "error", "warn", "skip", "info")
    )
    assert any(c[0] == "delete" for c in fake.calls)
    assert validator._created == []


def test_displacement_sentinel_creates_node():
    fake = make_fake_cmds(plugin_loaded=True)
    validator = ConfigValidator(cmds_module=fake, logger=Logger())
    config = ConfigLoader().get_material_config("aiStandardSurface")
    assert config.displacement_node_type == "displacementShader"
    validator._validate_displacement(config, "material/aiStandardSurface")
    infos = [r for r in validator._results if r.level == LogLevel.INFO]
    assert any("sentinel" in r.detail for r in infos)
    assert any("node_type 'displacementShader' created" in r.detail for r in validator._results)
    assert all(r.level != LogLevel.ERROR for r in validator._results)