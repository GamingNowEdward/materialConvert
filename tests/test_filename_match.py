"""Filename matching rules shared by the Batch Builder scanner and Colorspace."""

from core.config_loader import ConfigLoader
from core.filename_match import (
    ChannelMatcher,
    find_alias,
    normalize_stem,
    quality_key,
    shared_keywords,
)


def _matcher():
    return ChannelMatcher(ConfigLoader().get_texture_channels())


# --------------------------------------------------------------------------- #
# normalize_stem / find_alias
# --------------------------------------------------------------------------- #

def test_normalize_stem_folds_separators_and_case():
    assert normalize_stem("Hero-Base Color") == "hero_base_color"


def test_find_alias_short_only_token_match():
    assert find_alias("hero_metallic", "met") is None
    assert find_alias("hero_met", "met") == (5, 8)


def test_find_alias_long_skips_underscores_with_boundary():
    assert find_alias("hero_met_allic_01", "metallic") == (5, 14)
    assert find_alias("hero_metallic", "metallic") == (5, 13)
    assert find_alias("hero_metallicx", "metallic") is None
    assert find_alias("heroxmetallic", "metallic") is None


def test_find_alias_ignores_underscores_in_the_alias():
    # an alias may itself contain underscores; both spellings are one token
    assert find_alias("hero_met_allic_01", "met_allic") == (5, 14)
    assert find_alias("hero_metallic", "met_allic") == (5, 13)
    assert find_alias("hero_met_allic", "metallic") == (5, 14)


def test_find_alias_rejects_an_all_underscore_alias():
    assert find_alias("hero_metallic", "____") is None


def test_find_alias_handles_repeated_and_leading_trailing_underscores():
    assert find_alias("hero__col", "col") == (6, 9)
    assert find_alias("hero_col_", "col") == (5, 8)
    assert find_alias("__col", "col") == (2, 5)


def test_find_alias_numeric_suffix_token():
    assert find_alias("hero_nrm16", "nrm") == (5, 10)
    assert find_alias("hero_disp16", "disp") == (5, 11)
    assert find_alias("hero_col16", "col") == (5, 10)
    assert find_alias("hero_rough4k", "rough") == (5, 12)
    # a longer word that merely starts with an alias is not a match
    assert find_alias("hero_specular", "spec") is None


# --------------------------------------------------------------------------- #
# quality_key / shared_keywords
# --------------------------------------------------------------------------- #

def test_quality_key_reads_depth_and_resolution():
    assert quality_key("rock_NRM16_2K") == (16, 2)
    assert quality_key("rock_disp16") == (16, 0)
    assert quality_key("rock_rough_4k") == (0, 4)
    assert quality_key("rock_basecolor") == (0, 0)
    # numbers the whole set shares must not be mistaken for a bit depth
    assert quality_key("FabricCottonMuslin004_basecolor") == (0, 0)


def test_shared_keywords_rule():
    keywords = {"metalness", "col", "nrm", "roughness"}

    stems = ["a_col_2k_metalness", "b_nrm16_2k_metalness", "c_rough_2k_metalness"]
    # a keyword only counts when it is in the given set and shared by most files
    assert shared_keywords(stems, keywords) == {"metalness"}
    assert shared_keywords(stems, {"col", "nrm", "roughness"}) == set()
    # two files are too few for "shared by most files" to mean anything
    assert shared_keywords(stems[:2], keywords) == set()


def test_shared_keywords_boundary_and_numeric_suffixes():
    # 3 of 5 = 60%: exactly at the threshold
    assert shared_keywords(
        ["a_metalness", "b_metalness", "c_metalness", "d_roughness", "e_roughness"],
        {"metalness", "roughness"}) == {"metalness"}
    # a numeric suffix glued to the keyword still counts
    assert shared_keywords(
        ["a_nrm16", "b_nrm", "c_nrm4k", "d_nrm", "e_nrm"], {"nrm"}) == {"nrm"}


# --------------------------------------------------------------------------- #
# ChannelMatcher
# --------------------------------------------------------------------------- #

def test_matcher_exposes_every_alias():
    matcher = _matcher()
    assert "basecolor" in matcher.aliases
    # short aliases are part of the shared rule set too
    assert {"col", "sss", "nrm", "disp", "mask"} <= matcher.aliases


def test_matcher_returns_every_matched_channel_longest_first():
    matches = _matcher().matches_normalized("fabric_col_2k_metalness")

    assert [match.alias for match in matches] == ["metalness", "col"]
    assert {match.channel for match in matches} == {"Metallic", "BaseColor"}


def test_matcher_reports_common_attr_and_type():
    match, = _matcher().matches_normalized("rock_nrm16_2k")

    assert (match.channel, match.common_attr, match.channel_type) == (
        "Normal", "normal_bump", "normal")
    assert match.span == (5, 10)


def test_matcher_ignores_requested_aliases():
    matches = _matcher().matches_normalized("fabric_col_2k_metalness",
                                            ignore_aliases={"metalness"})

    assert [match.alias for match in matches] == ["col"]


def test_matcher_alias_of_token():
    matcher = _matcher()
    assert matcher.alias_of_token("col") == "col"
    assert matcher.alias_of_token("nrm16") == "nrm"
    assert matcher.alias_of_token("fabriccottonmuslin004") is None
    # token-bounded only: a short alias inside a word is not a match
    assert matcher.alias_of_token("school") is None


def test_matcher_ignores_a_non_object_channel_definition():
    matcher = ChannelMatcher({"Broken": "not an object",
                              "BaseColor": {"aliases": ["basecolor"],
                                            "common_attr": "baseColor",
                                            "type": "color"}})

    matches = matcher.matches_normalized("rock_basecolor")
    assert [match.channel for match in matches] == ["BaseColor"]
