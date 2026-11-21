ALTER TABLE public."transaction"
    ADD COLUMN review_flags jsonb NOT NULL DEFAULT '[]'::jsonb;
