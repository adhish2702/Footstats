import pg from "pg";

// PostgreSQL returns numeric and bigint (count(*)) as strings to avoid losing
// precision. Every number in this database fits comfortably in a double.
pg.types.setTypeParser(pg.types.builtins.NUMERIC, (v) => Number.parseFloat(v));
pg.types.setTypeParser(pg.types.builtins.INT8, (v) => Number.parseInt(v, 10));

export type Db = Pick<pg.Pool, "query">;

export function createPool(connectionString: string): pg.Pool {
  return new pg.Pool({
    connectionString,
    max: 5,
    idleTimeoutMillis: 30_000,
    // The API never writes: every session is made read-only as a second line of
    // defence. The pool waits for this before handing the connection out.
    onConnect: async (client) => {
      await client.query("SET default_transaction_read_only = on");
    },
  });
}
