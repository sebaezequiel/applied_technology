-- =============================================================
-- ETL Inteligente de Facturas — Migración inicial
-- Ejecutar una sola vez en el SQL Editor de Supabase
-- =============================================================

-- Tabla principal de facturas estructuradas
CREATE TABLE IF NOT EXISTS invoices (

    -- Identificador y auditoría
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Referencia al archivo original en MinIO
    storage_key     TEXT NOT NULL,

    -- Datos del comprobante
    invoice_number  TEXT,
    invoice_date    DATE,

    -- Emisor (proveedor)
    vendor_name     TEXT NOT NULL,
    vendor_tax_id   TEXT,

    -- Receptor (cliente)
    client_name     TEXT,
    client_tax_id   TEXT,

    -- Líneas de detalle almacenadas como JSONB
    -- Estructura de cada item: { description, quantity, unit_price, total }
    items           JSONB NOT NULL DEFAULT '[]',

    -- Totales
    subtotal        NUMERIC(14, 2),
    tax_amount      NUMERIC(14, 2),
    total_amount    NUMERIC(14, 2) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'ARS',

    -- Información adicional
    payment_method  TEXT,
    notes           TEXT
);

-- -------------------------------------------------------------
-- Índices para búsquedas frecuentes
-- -------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_invoices_vendor_name  ON invoices (vendor_name);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_date ON invoices (invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at   ON invoices (created_at DESC);

-- -------------------------------------------------------------
-- Comentarios descriptivos (documentación en la DB)
-- -------------------------------------------------------------
COMMENT ON TABLE  invoices                IS 'Facturas extraídas automáticamente por el pipeline ETL (OCR + LLM).';
COMMENT ON COLUMN invoices.storage_key    IS 'Clave del archivo original en MinIO/S3.';
COMMENT ON COLUMN invoices.items          IS 'Array JSON con las líneas de detalle de la factura.';
COMMENT ON COLUMN invoices.total_amount   IS 'Monto total a pagar incluyendo impuestos.';
COMMENT ON COLUMN invoices.currency       IS 'Código ISO 4217 de la moneda (ARS, USD, EUR, etc.).';
