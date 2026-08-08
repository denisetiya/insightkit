/* InsightKit demo dataset (SQLite) */
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  city TEXT
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers(id),
  status TEXT,
  amount REAL,
  created_at TEXT
);

INSERT INTO customers (id, name, email, city) VALUES
  (1, 'Alice', 'alice@example.com', 'Jakarta'),
  (2, 'Bob', 'bob@example.com', 'Bandung'),
  (3, 'Carol', 'carol@example.com', 'Jakarta');

INSERT INTO orders (id, customer_id, status, amount, created_at) VALUES
  (1, 1, 'paid', 150.0, '2026-07-01'),
  (2, 2, 'pending', 75.0, '2026-07-02'),
  (3, 1, 'refunded', 20.0, '2026-06-15'),
  (4, 3, 'paid', 200.0, '2026-07-05'),
  (5, 2, 'paid', 50.0, '2026-07-10');
