-- Required application reference data; safe to rerun. No demo/customer data.
BEGIN;
INSERT INTO public.categories (id, label, sort_order) VALUES
    ('connectivity', 'Connectivity', 1),
    ('performance', 'Performance & memory', 2),
    ('queries', 'Queries & indexes', 3),
    ('replication', 'Replication & sharding', 4),
    ('security', 'Security & access', 5),
    ('backup', 'Backup & restore', 6),
    ('drivers', 'Drivers & SDKs', 7),
    ('any', 'any', 8)
ON CONFLICT (id) DO UPDATE
SET label = EXCLUDED.label, sort_order = EXCLUDED.sort_order;
COMMIT;
