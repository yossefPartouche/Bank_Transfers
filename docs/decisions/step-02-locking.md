# Step 2 · Stopping overdrafts

## The problem
20 transfers leave the same account at once. Each one reads the balance, sees enough money,
and goes ahead. They all read the same old value, so several pass and the account goes negative.

## What we chose: lock the row
We read the balance with `SELECT … FOR UPDATE`. The other transfers on that account now wait
their turn, then read the real balance and decide on it. Simple to read, easy to explain.
The price: transfers on a busy account queue up, and locking A→B and B→A in opposite order
can deadlock (that's step 3).

## What we didn't choose (yet): a conditional update
`UPDATE … SET balance = balance - x WHERE balance >= x` checks and debits in one statement,
no read needed. Faster, but the rule hides in SQL and "0 rows updated" can mean two things.
We'll benchmark it against the lock later.