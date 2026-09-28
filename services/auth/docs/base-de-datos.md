# Conexión y migraciones, paso a paso

## Decisión vigente: solo PostgreSQL

El usuario decidió continuar únicamente con PostgreSQL. SQL Server queda como
objetivo futuro, no soportado hoy. Revisión realizada (compilando el DDL con el
dialecto mssql, sin conexión real): la aplicación no usa SQL nativo de PostgreSQL.

Checklist para cuando se active SQL Server:

1. Seguir sin SQL nativo de PostgreSQL en código y migraciones.
2. Migraciones: la cadena actual no corre en SQL Server, porque 05514603cf38
   elimina `users_normalized_email_key`, un nombre generado por PostgreSQL.
   Habrá que corregirla o reconstruirla, idealmente con naming_convention.
3. Texto humano (nombres, apellidos) como Unicode/NVARCHAR; String genera VARCHAR.
4. Declarar pyodbc, instalar ODBC Driver 18 y permitir configurar
   TrustServerCertificate por entorno (solo en local).
5. Validar conexión, `alembic upgrade head` sobre una base vacía y pruebas de
   concurrencia (READ_COMMITTED_SNAPSHOT, bloqueos).

## Actualización: schema auth configurado en los modelos

Base, en app/models/entities.py, ahora declara:

```python
metadata = MetaData(schema="auth")
```

Todas sus tablas, incluidos logs y catálogos, heredan auth. Las claves foráneas
locales como ForeignKey("users.id") se resuelven contra auth.users; lo mismo
ocurre con las claves compuestas. No hace falta repetir __table_args__ con el
schema en cada clase. No declarar otro Base para modelos nuevos.

El migrations/env.py actual utiliza include_schemas=True y un filtro include_name:
solo inspecciona auth y tablas presentes en Base.metadata. Una tabla que desaparezca
del modelo no se propone eliminar automáticamente. No reemplazar este env.py con
el ejemplo histórico más abajo, que no incluye el filtro.

Estado: migraciones aplicadas en PostgreSQL hasta `8baed1d57096` (head):

| Revisión | Contenido |
| --- | --- |
| f90d2c4ddbeb | Crea el schema auth y todas las tablas iniciales |
| 05514603cf38 | Elimina users.normalized_email (la normalización queda en el service) |
| 4188b68e5210 | Unicidad de users.email |
| 81b88abef3a5 | Elimina sessions.csrf_hash (Bearer sin cookies: no hay CSRF) |
| b902cd601f20 | Agrega users.is_platform_admin y lo otorga una vez al admin creado por el seed (con evento en change_history) |
| 37ba63fd1552 | Agrega roles.name: nullable → relleno con el código → NOT NULL |
| 28950766fbb9 | countries, identity_document_types, user_identity_documents, api_keys; birth_date y nationality_country_code en user_profiles |
| b920b3502d47 | Agrega api_keys.description (opcional) |
| 8baed1d57096 | Retira auth.logs, auth.logs_detail y auth.logs_steps (vacías): los logs pasan al schema audit |

Schema `audit` (logs): lo migra el paquete compartido, no el Alembic de auth. Después de
`python -m alembic upgrade head`, ejecutar `python scripts/migrate_audit.py` (idempotente).
Su versión vive en `audit.alembic_version` (hoy `38dd37f41c1e`), separada de la de auth.

La primera revisión ya crea el schema antes de las tablas, con este patrón:

```python
from sqlalchemy.schema import CreateSchema

def upgrade():
    op.execute(CreateSchema("auth"))
    # Después, las llamadas op.create_table(..., schema="auth") de la revisión.
```

No repetir CreateSchema en revisiones nuevas: el schema ya existe.
CreateSchema produce SQL para el dialecto seleccionado sin escribir SQL propio
de PostgreSQL. La compilación no sustituye una prueba real en SQL Server.

La tabla técnica alembic_version conserva por ahora el schema predeterminado de
la conexión (normalmente public en PostgreSQL, dbo en SQL Server). No es un modelo
de negocio de auth. Mantener el schema predeterminado distinto de auth para que
la reflexión de Alembic no confunda nombres calificados con tablas sin schema.
Si otros servicios comparten la misma base, acordar tablas de versión independientes
antes de ejecutar sus migraciones; no compartir por accidente alembic_version.

Si ya hubiera tablas en public/dbo con datos, esta configuración no las traslada:
necesitarían una migración de traslado revisada, nunca borrarlas y recrearlas.

Referencias: [schemas de SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/metadata.html),
[filtros de Alembic](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

## Propuesta pendiente: convención de nombres de constraints

Sin convención, cada motor inventa el nombre de índices, UNIQUE, FK y CHECK
(por ejemplo `users_email_key` en PostgreSQL y otro distinto en SQL Server).
Alembic necesita el nombre para modificarlos o eliminarlos, y
`create_unique_constraint(None, ...)` no deja un nombre predecible.

SQLAlchemy permite fijarlos en el mismo MetaData del Base:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(schema="auth", naming_convention=NAMING_CONVENTION)
```

- `%(column_0_N_name)s` concatena todas las columnas: distingue las UNIQUE compuestas.
- `ck` exige dar `name=` a cada CheckConstraint (por ejemplo `name="max_sessions_positive"`).
- Nombres largos: PostgreSQL corta a 63 caracteres y SQL Server admite 128.
  Revisar los nombres generados de las FK compuestas.
- Afecta solo a constraints nuevos. Los existentes conservan su nombre;
  renombrarlos exige una migración revisada, por ejemplo con
  `op.execute("ALTER TABLE ... RENAME CONSTRAINT ...")` escrita para cada motor,
  o bien aceptar que los antiguos mantengan el nombre del motor.
- Al activarla, un `revision --autogenerate` puede proponer cambios de nombre:
  revisar el archivo antes de aplicar.

No está implementado; decidir antes de la siguiente migración.
Referencia: [convenciones de nombres](https://alembic.sqlalchemy.org/en/latest/naming.html).

## Guía de los pasos anteriores (ya completados)

Se conserva como explicación. Los pasos 1 a 6 ya se realizaron: motor corregido,
conexión comprobada, Alembic inicializado y migraciones aplicadas.

## 1. Corregir la selección del motor

En app/core/db/connection.py cambiar únicamente:

```python
if settings.DB_ENGINE == "postgresql":
```

Ahora dice "postgres", pero Settings admite "postgresql" o "mssql".
Con el valor actual se seleccionaría por error la rama SQL Server.
El driver PostgreSQL debe seguir siendo postgresql+psycopg, acorde con
psycopg[binary] declarado en requirements.txt.

## 2. Entorno y configuración

Ejecutar desde services/auth con el entorno activado:

```powershell
cd D:\proyectos\proyecto-general\services\auth
.\enviroment\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si no se desea activar el entorno, sustituir python en los comandos por
.\enviroment\Scripts\python.exe. No hace falta modificar la política de PowerShell.

La aplicación lee services/auth/.env, no el .env de proyecto-central.
El de Compose configura el servidor; el de auth indica cómo conectarse.
No publicar ni copiar contraseñas reales a la documentación.

| Variable | Propósito | Valor inicial o condición |
| --- | --- | --- |
| PROJECT_NAME | Nombre de la API | Auth |
| DB_ENGINE | Motor | postgresql; mssql será la alternativa |
| DB_HOST | Dirección del servidor | localhost desde Windows; db entre contenedores de la misma red |
| DB_PORT | Puerto de conexión | 5432 PostgreSQL; normalmente 1433 SQL Server |
| DB_NAME | Base de datos existente | Obligatoria |
| DB_USER | Usuario de conexión | Obligatorio |
| DB_PASSWORD | Contraseña | Obligatoria; SecretStr no es cifrado |
| CORS_ORIGINS | Orígenes web para el futuro middleware | Lista JSON, por ejemplo ["http://localhost:3000"] |

Cambiar DB_ENGINE no cambia automáticamente DB_PORT, no instala drivers y no
migra datos. Configurar una conexión no equivale a crear tablas.

## 3. Comprobar conexión sin crear tablas

Tras corregir el paso 1, pegar este bloque en PowerShell desde services/auth:

```powershell
@'
from sqlalchemy import text
from app.core.db.connection import engine

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()
        print(f"Conexion correcta. SELECT 1 = {result}")
finally:
    engine.dispose()
'@ | python -
```

Resultado esperado: Conexion correcta. SELECT 1 = 1.

- engine.connect abre una conexión real y verifica el acceso a la base configurada.
- text declara una sentencia SQL explícita; SELECT 1 funciona en ambos motores.
- scalar_one obtiene el único valor de la única fila esperada.
- with libera la conexión aunque la consulta falle.
- dispose cierra el pool de este proceso de prueba; no se llama por cada request.

No se usa Base.metadata.create_all ni se escribe información de negocio.
La prueba no valida modelos, permisos para crear tablas ni compatibilidad de migraciones.

Errores frecuentes:
- Falta DB_NAME/DB_USER/DB_PASSWORD: revisar el .env de auth.
- No module named psycopg: instalar requirements con el mismo Python que ejecuta la prueba.
- Intenta cargar pyodbc usando PostgreSQL: revisar DB_ENGINE y la condición del paso 1.
- Conexión rechazada: comprobar contenedor, host y puerto publicado.
- Autenticación fallida: comprobar credenciales. Cambiar el .env de Compose no cambia
  automáticamente contraseñas de una base ya inicializada en un volumen.

## 4. Instalar e inicializar Alembic

Solo después de comprobar conexión, añadir a requirements.txt:

```text
alembic>=1.16,<2
```

Después ejecutar desde services/auth:

```powershell
python -m pip install -r requirements.txt
python -m alembic init migrations
```

init prepara archivos locales; no crea las tablas de auth:

```text
services/auth/
  alembic.ini
  migrations/
    env.py
    script.py.mako
    versions/
```

Se inicializa una vez. Si migrations ya existe con archivos, revisar antes de
repetir o sobrescribir; no borrar contenido para forzar el comando.

- alembic.ini: ubicación y configuración de la herramienta.
- env.py: cómo conecta y qué modelos compara.
- script.py.mako: plantilla de nuevas migraciones.
- versions: historial de cambios estructurales, que se conserva con el código.

## 5. Conectar Alembic con nuestro código

Una vez generado, reemplazar migrations/env.py por este contenido mínimo:

```python
from alembic import context

from app.core.db.connection import database_url, engine
from app.models.entities import Base


# Importar entities registra sus tablas en el único Base del proyecto.
# No declarar otra clase Base aquí.
target_metadata = Base.metadata


def run_migrations_offline():
    """Genera SQL sin conectar; no permite comparar automáticamente con la BD."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Utiliza la misma configuración de conexión que auth."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Este env.py no utiliza sqlalchemy.url de alembic.ini. Se puede quitar esa línea
del archivo generado; no pegar credenciales allí. Se conserva script_location
apuntando a migrations. Ejecutar los comandos desde services/auth.

Si luego dividimos los modelos en archivos, habrá que importarlos antes de
usar Base.metadata para que Alembic conozca todas las tablas.

Para comprobar que Alembic carga configuración/modelos y conecta:

```powershell
python -m alembic current
```

Si todavía no se aplicó ninguna revisión puede no mostrar un identificador.
Eso no es un error si termina correctamente. No aplicar upgrade todavía.

## 6. Antes de generar y aplicar la primera migración

Resuelto: se retiraron las FK diferidas y el catálogo Actor. Los campos de
actor son FK nullable a users.id (ver modelo-datos.md). Sigue sin validarse
SQL Server.

Flujo para cada cambio de esquema:

```powershell
python -m alembic revision --autogenerate -m "descripcion del cambio"
# Revisar el archivo creado en migrations/versions antes del siguiente comando.
python -m alembic upgrade head
```

- revision --autogenerate compara modelos con la BD y escribe una propuesta en archivo.
- upgrade head aplica las revisiones pendientes: este sí modifica la estructura.
- No usar autogenerate sobre una BD con tablas de otros servicios sin definir
  previamente su alcance: podría proponer eliminarlas.
- Revisar nombres, constraints, operaciones de borrado y SQL para el motor elegido.
- No ejecutar downgrade destructivo: el proyecto conserva datos e historial;
  los cambios correctivos deben diseñarse expresamente.

No usar la plantilla multidb solo por admitir PostgreSQL o SQL Server.
Aquí se elige una base por despliegue; varias conexiones simultáneas son otro alcance.

## Sesiones y transacciones

SessionLocal crea una sesión ORM, distinta de la sesión de login AuthSession.
get_db se usará con Depends cuando existan rutas. Cierra la sesión al terminar,
pero no hace commit automático. Cada operación definirá una transacción para
confirmar juntos su cambio y el historial. Autoflush no equivale a commit.

UserService usa `with self.session.begin():`. Esto falla con
"A transaction is already begun" si antes, en la misma sesión, se ejecutó
una consulta (SQLAlchemy abre la transacción automáticamente). Cada request
debe llamar al service con una sesión sin consultas previas, o el service
debe revisarse cuando se combinen varias operaciones.

## Referencias

- [Alembic: inicialización y configuración](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic: revisión de migraciones autogeneradas](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [SQLAlchemy: conexiones y URL.create](https://docs.sqlalchemy.org/en/20/core/engines.html)
- [SQLAlchemy: ciclo de vida de sesiones](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
