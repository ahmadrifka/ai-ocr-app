ALTER TABLE public."transaction"
    ADD COLUMN IF NOT EXISTS transaction_id varchar(255);
