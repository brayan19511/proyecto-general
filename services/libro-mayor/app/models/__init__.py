# Importar este módulo registra las tablas del servicio en Base.metadata.
# Cada archivo nuevo de modelos debe importarse aquí para que Alembic lo vea.
from app.models.entities import (
    Account,
    Actor,
    Base,
    ChangeHistory,
    ClassificationRun,
    CostCenterMapping,
    ExpenseCategory,
    ExpenseRule,
    LedgerLine,
    SapCompany,
    SyncRun,
)
