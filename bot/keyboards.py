"""Inline keyboards and category hierarchy for Telegram Bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Full hierarchy (superset)
CATEGORY_HIERARCHY: dict[str, list[str]] = {
    "Persediaan": [
        "Bahan Baku",
    ],
    "Penjualan": [
        "Penjualan Produk",
    ],
    "Modal dan Prive": [
        "Modal",
        "Prive",
    ],
    "Beban Operasional": [
        "Biaya-Gaji Karyawan",
        "Biaya-Konsumsi",
        "Biaya-Perlengkapan Kantor dan Administrasi",
        "Biaya-Transportasi",
        "Biaya-Ongkir",
        "Biaya-Perbaikan Bangunan",
        "Biaya-Operasional",
        "Biaya-Sosial",
    ],
    "Utang/Piutang": [
        "Utang",
        "Piutang",
    ],
    "Aset Tetap/Investasi": [
        "Biaya-Pembelian Aset",
    ],
    "Pendapatan/Beban Lain": [
        "Beban Lain",
        "Pendapatan Lain",
    ],
    "Pajak": [
        "Pembayaran pajak",
    ],
    "Uncategorized": [
        "Uncategorized",
    ],
}

CATEGORIES: list[str] = list(CATEGORY_HIERARCHY.keys())

# Hierarchies filtered by transaction type
HIERARCHY_BY_TX_TYPE: dict[str, dict[str, list[str]]] = {
    "EXPENSES": {
        "Persediaan": [
            "Bahan Baku",
        ],
        "Modal dan Prive": [
            "Prive",
        ],
        "Beban Operasional": [
            "Biaya-Gaji Karyawan",
            "Biaya-Konsumsi",
            "Biaya-Perlengkapan Kantor dan Administrasi",
            "Biaya-Transportasi",
            "Biaya-Ongkir",
            "Biaya-Perbaikan Bangunan",
            "Biaya-Operasional",
            "Biaya-Sosial",
        ],
        "Utang/Piutang": [
            "Utang",
        ],
        "Aset Tetap/Investasi": [
            "Biaya-Pembelian Aset",
        ],
        "Pendapatan/Beban Lain": [
            "Beban Lain",
        ],
        "Pajak": [
            "Pembayaran pajak",
        ],
        "Uncategorized": [
            "Uncategorized",
        ],
    },
    "INCOMING": {
        "Penjualan": [
            "Penjualan Produk",
        ],
        "Modal dan Prive": [
            "Modal",
        ],
        "Utang/Piutang": [
            "Piutang",
        ],
        "Pendapatan/Beban Lain": [
            "Pendapatan Lain",
        ],
        "Uncategorized": [
            "Uncategorized",
        ],
    },
    "TRANSFER": {
        "Uncategorized": [
            "Uncategorized",
        ],
    },
}


def get_hierarchy_for_type(tx_type: str | None = None) -> dict[str, list[str]]:
    """Return category hierarchy filtered by transaction type, or full hierarchy if None."""
    if not tx_type:
        return CATEGORY_HIERARCHY
    return HIERARCHY_BY_TX_TYPE.get(tx_type.upper(), CATEGORY_HIERARCHY)


def build_confirmation_keyboard(tx_id: int, tx_type: str | None = None) -> InlineKeyboardMarkup:
    """Build confirmation inline keyboard with [ ✅ Sesuai ] and [ ✏️ Belum Sesuai ]."""
    edit_cb = f"tx_edit:{tx_id}:{tx_type}" if tx_type else f"tx_edit:{tx_id}"
    keyboard = [
        [
            InlineKeyboardButton("✅ Sesuai", callback_data=f"tx_confirm:{tx_id}"),
            InlineKeyboardButton("✏️ Belum Sesuai", callback_data=edit_cb),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_category_keyboard(tx_id: int, tx_type: str | None = None) -> InlineKeyboardMarkup:
    """Build category selection inline keyboard filtered by transaction type."""
    hierarchy = get_hierarchy_for_type(tx_type)
    allowed_categories = list(hierarchy.keys())

    keyboard: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in allowed_categories:
        idx = CATEGORIES.index(cat)
        cb_data = f"tx_cat:{tx_id}:{idx}:{tx_type}" if tx_type else f"tx_cat:{tx_id}:{idx}"
        row.append(InlineKeyboardButton(cat, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Batal / Kembali", callback_data=f"tx_back:{tx_id}")])
    return InlineKeyboardMarkup(keyboard)


def build_subcategory_keyboard(
    tx_id: int, cat_idx: int, tx_type: str | None = None
) -> InlineKeyboardMarkup:
    """Build subcategory selection inline keyboard based on selected category and transaction type."""
    cat_name = CATEGORIES[cat_idx]
    hierarchy = get_hierarchy_for_type(tx_type)
    subcategories = hierarchy.get(cat_name, CATEGORY_HIERARCHY.get(cat_name, []))

    keyboard: list[list[InlineKeyboardButton]] = []
    for sub in subcategories:
        sub_idx = CATEGORY_HIERARCHY[cat_name].index(sub)
        keyboard.append(
            [InlineKeyboardButton(sub, callback_data=f"tx_sub:{tx_id}:{cat_idx}:{sub_idx}")]
        )

    back_cb = f"tx_edit:{tx_id}:{tx_type}" if tx_type else f"tx_edit:{tx_id}"
    keyboard.append([InlineKeyboardButton("🔙 Pilih Kategori Lain", callback_data=back_cb)])
    return InlineKeyboardMarkup(keyboard)
