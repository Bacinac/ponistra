from django.db import migrations

# SUM's addition (values.total), which no SQL aggregate does: each sum whose terms cancel to
# within 2^-48 of the larger is 0. A term Postgres could not add without stopping the query
# (beyond 8E307, or a cancellation of numbers too small to measure it by) makes the total NaN,
# which the final function turns into NULL, so that Python computes the cell.
TOTAL = """
CREATE FUNCTION engine_total_step(total float8, term float8) RETURNS float8
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    result float8;
BEGIN
    IF total = 'NaN'::float8 THEN
        RETURN total;
    END IF;
    IF abs(total) >= 8e307 OR abs(term) >= 8e307 THEN
        RETURN 'NaN'::float8;
    END IF;
    result := total + term;
    IF (total < 0) = (term < 0) THEN
        RETURN result + 0;
    END IF;
    IF greatest(abs(total), abs(term)) < 1e-300 THEN
        RETURN 'NaN'::float8;
    END IF;
    IF abs(result) < greatest(abs(total), abs(term)) * 3.552713678800501e-15 THEN
        RETURN 0;
    END IF;
    RETURN result + 0;
END
$$;

CREATE FUNCTION engine_total_final(total float8) RETURNS float8
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN CASE WHEN total = 'NaN'::float8 THEN NULL ELSE total END;

CREATE AGGREGATE engine_total(float8) (
    SFUNC = engine_total_step,
    STYPE = float8,
    INITCOND = '0',
    FINALFUNC = engine_total_final
);
"""

DROP = """
DROP AGGREGATE engine_total(float8);
DROP FUNCTION engine_total_final(float8);
DROP FUNCTION engine_total_step(float8, float8);
"""


class Migration(migrations.Migration):
    operations = [migrations.RunSQL(TOTAL, DROP)]
