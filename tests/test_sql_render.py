import pytest

from core.sql_render import (
    safe_identifier,
    safe_identifier_list,
    safe_fq_name,
    safe_literal,
    safe_literal_list,
    render,
)


class TestSafeIdentifier:
    def test_valid_identifier_is_quoted_and_uppercased(self):
        assert safe_identifier("order_id") == '"ORDER_ID"'
        assert safe_identifier("ORDER_ID") == '"ORDER_ID"'
        assert safe_identifier("_col$1") == '"_COL$1"'

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            None,
            "1col",  # can't start with a digit
            "col name",  # space
            "col;DROP TABLE x",  # injection attempt
            "col'--",
            "col.other",  # dot -- not a single identifier
            123,  # not a string
        ],
    )
    def test_rejects_unsafe_or_invalid_input(self, bad):
        with pytest.raises(ValueError):
            safe_identifier(bad)


class TestSafeIdentifierList:
    def test_joins_multiple_identifiers(self):
        assert safe_identifier_list(["a", "b"]) == '"A", "B"'

    def test_rejects_bare_string_instead_of_list(self):
        # Regression test: a string is iterable, so this used to silently
        # explode into one quoted identifier per character instead of
        # raising a clear error.
        with pytest.raises(ValueError, match="Expected a list"):
            safe_identifier_list("ORDER_ID")

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match="non-empty"):
            safe_identifier_list([])

    def test_rejects_non_iterable(self):
        with pytest.raises(ValueError):
            safe_identifier_list(None)


class TestSafeFqName:
    def test_valid_three_part_name(self):
        assert safe_fq_name("db.schema.table") == '"DB"."SCHEMA"."TABLE"'

    def test_valid_single_part_name(self):
        assert safe_fq_name("table") == '"TABLE"'

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            None,
            "db..table",  # empty part
            "db.schema.",  # trailing dot
            "db.sch ema.table",  # space in a part
            "db.schema.table; DROP TABLE x; --",
            123,
        ],
    )
    def test_rejects_unsafe_or_invalid_input(self, bad):
        with pytest.raises(ValueError):
            safe_fq_name(bad)


class TestSafeLiteral:
    def test_none_becomes_null(self):
        assert safe_literal(None) == "NULL"

    def test_bool(self):
        assert safe_literal(True) == "TRUE"
        assert safe_literal(False) == "FALSE"

    def test_numbers_are_unquoted(self):
        assert safe_literal(42) == "42"
        assert safe_literal(3.5) == "3.5"

    def test_string_is_quoted(self):
        assert safe_literal("hello") == "'hello'"

    def test_embedded_quote_is_escaped(self):
        assert safe_literal("O'Brien") == "'O''Brien'"

    def test_injection_attempt_is_neutralized_as_a_literal(self):
        malicious = "x'; DROP TABLE dq_results; --"
        rendered = safe_literal(malicious)
        # The single quote is doubled (escaped), not left as a raw
        # string-terminator -- the whole thing stays inside one literal.
        assert rendered == "'x''; DROP TABLE dq_results; --'"
        assert rendered.count("'") % 2 == 0


class TestSafeLiteralList:
    def test_joins_multiple_literals(self):
        assert safe_literal_list(["OPEN", "CLOSED"]) == "'OPEN', 'CLOSED'"

    def test_rejects_bare_string_instead_of_list(self):
        with pytest.raises(ValueError, match="Expected a list"):
            safe_literal_list("OPEN")

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match="non-empty"):
            safe_literal_list([])


class TestRender:
    def test_fills_placeholders(self):
        assert render("SELECT {col} FROM {table}", {"col": '"X"', "table": '"T"'}) == 'SELECT "X" FROM "T"'

    def test_missing_placeholder_raises_value_error(self):
        with pytest.raises(ValueError, match="missing placeholder"):
            render("SELECT {col} FROM {table}", {"col": '"X"'})
