"""Tipos de documento SAP que se pueden buscar y cuyos anexos se pueden descargar.

El front envía el código propio (FV, OC, ...), nunca un nombre de SAP: el
contrato no cambia si la fuente pasa de Service Layer a HANA. Cada fuente toma
de aquí su nombre (sl_entity para Service Layer, hana_table para HANA).

Es una lista blanca en código, no una tabla: los nombres de SAP terminan dentro
de una URL o de una consulta, y agregar un tipo exige revisar sus campos.
Origen: notebook obtener_documentos.ipynb (consultas-rash).
"""

from dataclasses import dataclass

# Criterios de búsqueda exacta (uno por búsqueda).
DOC_ENTRY = "doc_entry"  # Id interno.
DOC_NUM = "doc_num"  # Número que ve el usuario (p. ej. número de OC).
NUM_AT_CARD = "num_at_card"  # Referencia del cliente/proveedor (texto libre).
FOLIO = "folio"  # Serie-número, p. ej. F001-00047012.

ALL_CRITERIA = (DOC_ENTRY, DOC_NUM, NUM_AT_CARD, FOLIO)


@dataclass(frozen=True)
class DocumentType:
    code: str
    label: str
    sl_entity: str  # Colección del Service Layer.
    hana_table: str  # Tabla de cabecera (para una futura fuente HANA).
    partner: str  # "customer", "supplier" o "none": cómo se rotula CardCode/CardName en el front.
    criteria: tuple[str, ...] = ALL_CRITERIA


DOCUMENT_TYPES: dict[str, DocumentType] = {
    t.code: t
    for t in (
        DocumentType("OC", "Orden de compra", "PurchaseOrders", "OPOR", "supplier"),
        DocumentType("EM", "Entrada de mercancía", "PurchaseDeliveryNotes", "OPDN", "supplier"),
        DocumentType("FC", "Factura de proveedor", "PurchaseInvoices", "OPCH", "supplier"),
        DocumentType("NCC", "Nota de crédito de proveedor", "PurchaseCreditNotes", "ORPC", "supplier"),
        DocumentType("OV", "Orden de venta", "Orders", "ORDR", "customer"),
        DocumentType("GR", "Entrega / guía de remisión", "DeliveryNotes", "ODLN", "customer"),
        DocumentType("FV", "Factura de cliente", "Invoices", "OINV", "customer"),
        DocumentType("NCV", "Nota de crédito de cliente", "CreditNotes", "ORIN", "customer"),
        DocumentType("COT", "Oferta de venta", "Quotations", "OQUT", "customer"),
        # Por confirmar en el Service Layer real si exponen NumAtCard y el folio.
        DocumentType("TR", "Transferencia de stock", "StockTransfers", "OWTR", "none", (DOC_ENTRY, DOC_NUM)),
        DocumentType("SM", "Salida de mercancía", "InventoryGenExits", "OIGE", "none", (DOC_ENTRY, DOC_NUM)),
    )
}
