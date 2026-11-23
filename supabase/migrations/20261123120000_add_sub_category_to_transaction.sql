-- Add sub_category column to transaction table
ALTER TABLE public."transaction"
    ADD COLUMN sub_category varchar(100) NOT NULL DEFAULT 'Uncategorized';

-- Backfill: copy old category values into sub_category (they were sub-category level)
UPDATE public."transaction" SET sub_category = category;

-- Remap category to parent categories based on old sub-category values
UPDATE public."transaction" SET category = 'Persediaan' WHERE sub_category = 'Bahan Baku';
UPDATE public."transaction" SET category = 'Beban Operasional' WHERE sub_category IN (
    'Biaya-Gaji Karyawan', 'Biaya-Konsumsi',
    'Biaya-Perlengkapan Kantor dan Administrasi',
    'Biaya-Transportasi', 'Biaya-Ongkir',
    'Biaya-Perbaikan Bangunan', 'Biaya-Operasional', 'Biaya-Sosial'
);
UPDATE public."transaction" SET category = 'Aset Tetap/Investasi' WHERE sub_category = 'Biaya-Pembelian Aset';
UPDATE public."transaction" SET category = 'Penjualan', sub_category = 'Penjualan Produk' WHERE sub_category = 'sale';
-- Rows with 'Uncategorized' keep category='Uncategorized', sub_category='Uncategorized'
