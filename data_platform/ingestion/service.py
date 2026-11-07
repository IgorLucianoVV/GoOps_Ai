"""Registro de fontes (L0) e ingestão para a camada Bronze (L1)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import Conflict, GoOpsError, NotFound, ValidationError
from goops_core.permissions import Principal, require_permission
from goops_core.util import jdump, jload, new_id, now_iso

from ..catalog import register_dataset
from ..connectors.registry import CONNECTORS, build_connector
from ..lineage.registry import add_edge
from ..storage import Lakehouse

log = logging.getLogger("goops.ingestion")
ENTITIES = ("orders", "nps", "deliveries", "custom")
ENTITY_LABEL = {"orders": "API de Pedidos", "nps": "API de Avaliações/NPS", "deliveries": "API de Entregas/Logística",
                "custom": "Fonte de setor (conjunto configurável)"}
_FORBIDDEN_CONFIG_KEYS = ("password", "token", "secret", "api_key", "apikey")


def _check_no_inline_secrets(config: Any, path: str = "") -> None:
    if isinstance(config, dict):
        for k, v in config.items():
            lk = str(k).lower()
            if any(f in lk for f in _FORBIDDEN_CONFIG_KEYS) and not lk.endswith("_env") and v:
                raise ValidationError(f"Credencial inline proibida em '{path + k}'. Use uma variável de ambiente (*_env).")
            _check_no_inline_secrets(v, f"{path}{k}.")


def _validate_profile(config: Dict[str, Any], db: Optional[Database] = None) -> None:
    from ..silver.mappings import PROFILES
    from ..silver.profiles import profile_exists
    profile = config.get("mapping_profile", "default")
    if profile in PROFILES or (db is not None and profile_exists(db, profile)):
        return
    raise ValidationError(f"Perfil de mapeamento inválido: {profile}. Crie-o em Data Lakehouse › Mapeamentos.")


GOCASE_SEED = {
    "orders": ("gocase_orders", "Gocase · Base Pedidos (planilha do case)", "seed/gocase/pedidos.xlsx", []),
    "nps": ("gocase_nps", "Gocase · Base de NPS (planilha do case)", "seed/gocase/nps.xlsx", ["Name", "Ipaddress"]),
    "deliveries": ("gocase_deliveries", "Gocase · Base de entregas (planilha do case)", "seed/gocase/entregas.xlsx", []),
}


# Complemento SINTÉTICO (is_demo): preenche lacunas das planilhas (datas de envio/previsão/entrega) e adiciona
# pedidos fictícios em trânsito. Pode ser desativado em Lakehouse › Fontes para ver só os dados reais.
GOCASE_COMPLEMENT = [
    ("gocase_complemento_datas_entrega", "Complemento sintético · datas de envio/previsão/entrega", "deliveries",
     {"kind": "delivery_dates", "role": "complement"}),
    ("gocase_demo_pedidos_transito", "Demo sintética · pedidos em trânsito", "orders", {"kind": "transit_orders"}),
    ("gocase_demo_entregas_transito", "Demo sintética · entregas em trânsito", "deliveries", {"kind": "transit_deliveries"}),
]


def gocase_seed_available() -> bool:
    from ..connectors.file_connector import import_dir
    return all((import_dir() / path).exists() for _, _, path, _ in GOCASE_SEED.values())


def seed_gocase_sources(db: Database, actor: Principal) -> None:
    """Fontes da seed padrão: planilhas reais do case Gocase (conector 'file', perfil 'gocase_xlsx')."""
    for entity, (key, name, path, exclude) in GOCASE_SEED.items():
        if db.fetchone("SELECT id FROM sources WHERE key = ?", (key,)):
            continue
        create_source(db, actor, key=key, name=name, entity=entity, connector="file",
                      config={"path": path, "format": "xlsx", "exclude_fields": exclude, "mapping_profile": "gocase_xlsx",
                              "schema_version": "gocase-xlsx-1", "seed": True}, is_demo=False)
    for key, name, entity, cfg in GOCASE_COMPLEMENT:
        if db.fetchone("SELECT id FROM sources WHERE key = ?", (key,)):
            continue
        create_source(db, actor, key=key, name=name, entity=entity, connector="gocase_complement",
                      config={**cfg, "seed": 42, "mapping_profile": "default", "seed_source": True}, is_demo=True)
    from ..sectors.example import seed_reputation_sector
    seed_reputation_sector(db)                     # setor de exemplo 100% configurável (ReclameAqui)
    apply_features(db)                             # setor Estoque (Desafio 2) conforme Configurações › Recursos


def _source_row(r: dict) -> dict:
    r["config"] = jload(r["config"], {})
    r["is_demo"] = bool(r["is_demo"])
    return r


def list_sources(db: Database) -> List[dict]:
    rows = [_source_row(r) for r in db.fetchall("SELECT * FROM sources ORDER BY created_at")]
    for r in rows:
        r["last_run"] = db.fetchone("SELECT id, status, records_ingested, records_failed, started_at, finished_at, error "
                                    "FROM ingestion_runs WHERE source_key = ? ORDER BY started_at DESC LIMIT 1", (r["key"],))
    return rows


def get_source(db: Database, key_or_id: str) -> dict:
    r = db.fetchone("SELECT * FROM sources WHERE key = ? OR id = ?", (key_or_id, key_or_id))
    if not r:
        raise NotFound(f"Fonte {key_or_id} não encontrada.")
    return _source_row(r)


def create_source(db: Database, actor: Principal, *, key: str, name: str, entity: str, connector: str,
                  config: Dict[str, Any], is_demo: bool = False) -> dict:
    require_permission(actor, "data:write")
    if not key or not key.replace("_", "").isalnum() or len(key) > 60:
        raise ValidationError("Chave da fonte inválida (use letras, números e _).")
    if entity not in ENTITIES:
        raise ValidationError(f"Entidade inválida. Suportadas nesta versão: {', '.join(ENTITIES)}")
    if connector not in CONNECTORS:
        raise ValidationError(f"Conector inválido: {connector}")
    _check_no_inline_secrets(config)
    if connector == "http_json" and not str(config.get("base_url", "")).startswith(("https://", "http://")):
        raise ValidationError("Conector http_json exige 'base_url' real (http/https) fornecida pelo responsável da API.")
    _validate_profile(config, db)
    if connector in ("file", "http_json"):
        build_connector(key, connector, {**config, "entity": entity})  # valida caminho/formato/URL/credencial
    if db.fetchone("SELECT id FROM sources WHERE key = ?", (key,)):
        raise Conflict("Já existe uma fonte com esta chave.")
    config = {**config, "entity": entity}
    source_id = new_id("SRC")
    db.execute("INSERT INTO sources (id, key, name, entity, connector, config, status, is_demo, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
               (source_id, key, name, entity, connector, jdump(config), int(is_demo), now_iso()))
    add_edge(db, f"source:{key}", f"bronze:{key}", "ingestion (append-only JSONL)")
    record_audit(db, actor, "source.create", "source", source_id, {"key": key, "connector": connector})
    return get_source(db, source_id)


def update_source(db: Database, actor: Principal, key: str, *, name: Optional[str] = None,
                  config: Optional[Dict[str, Any]] = None, status: Optional[str] = None) -> dict:
    """Edita nome, configuração ou status (active/inactive) de uma fonte. Cursor incremental é preservado."""
    require_permission(actor, "data:write")
    src = get_source(db, key)
    sets, params = [], []
    if name is not None:
        if not 3 <= len(name) <= 120:
            raise ValidationError("Nome deve ter entre 3 e 120 caracteres.")
        sets.append("name = ?"); params.append(name)
    if status is not None:
        if status not in ("active", "inactive"):
            raise ValidationError("Status deve ser 'active' ou 'inactive'.")
        sets.append("status = ?"); params.append(status)
    if config is not None:
        _check_no_inline_secrets(config)
        _validate_profile(config, db)
        if src["connector"] == "http_json" and not str(config.get("base_url", "")).startswith(("https://", "http://")):
            raise ValidationError("Conector http_json exige 'base_url' real (http/https).")
        build_connector(src["key"], src["connector"], {**config, "entity": src["entity"]})  # valida a configuração
        sets.append("config = ?"); params.append(jdump({**config, "entity": src["entity"]}))
    if not sets:
        return get_source(db, key)
    sets.append("updated_at = ?"); params.append(now_iso())
    db.execute(f"UPDATE sources SET {', '.join(sets)} WHERE id = ?", (*params, src["id"]))
    record_audit(db, actor, "source.update", "source", src["id"],
                 {"name": name, "status": status, "config_changed": config is not None})
    return get_source(db, key)


def reset_cursor(db: Database, actor: Principal, key: str) -> dict:
    require_permission(actor, "data:write")
    src = get_source(db, key)
    db.execute("UPDATE sources SET cursor = NULL, updated_at = ? WHERE id = ?", (now_iso(), src["id"]))
    record_audit(db, actor, "source.cursor_reset", "source", src["id"], {})
    return get_source(db, key)


def seed_demo_sources(db: Database, actor: Principal, scenario: str = "full") -> None:
    for entity in ("orders", "nps", "deliveries"):
        key = f"demo_{entity}"
        if db.fetchone("SELECT id FROM sources WHERE key = ?", (key,)):
            continue
        create_source(db, actor, key=key, name=f"{ENTITY_LABEL[entity]} (DEMO)", entity=entity, connector="demo",
                      config={"scenario": scenario, "seed": 42, "page_size": 500, "seed_source": True}, is_demo=True)
    if scenario != "basic10":
        apply_features(db)   # Atendimento (Desafio 1): fonte de contatos sintéticos ligada aos pedidos de demo


def test_source(db: Database, actor: Principal, key: str) -> dict:
    require_permission(actor, "data:read")
    src = get_source(db, key)
    try:
        result = build_connector(src["key"], src["connector"], src["config"]).test_connection()
        ok = True
    except GoOpsError as exc:
        result, ok = {"error": exc.message}, False
    record_audit(db, actor, "source.test", "source", src["id"], {"ok": ok})
    return {"source": src["key"], "ok": ok, "result": result}


def sync_source(db: Database, lake: Lakehouse, actor: Principal, key: str, full_refresh: bool = False) -> dict:
    require_permission(actor, "data:sync")
    src = get_source(db, key)
    if src["status"] != "active":
        raise Conflict(f"Fonte {key} não está ativa.")
    run_id = new_id("ING")
    cursor_before = None if full_refresh else src.get("cursor")
    db.execute("INSERT INTO ingestion_runs (id, source_key, started_at, status, cursor_before, triggered_by, is_demo) "
               "VALUES (?, ?, ?, 'running', ?, ?, ?)",
               (run_id, src["key"], now_iso(), cursor_before, actor.actor_label, int(src["is_demo"])))
    try:
        connector = build_connector(src["key"], src["connector"], src["config"])
        result = connector.fetch(since=cursor_before)
        written = lake.write_bronze(src["key"], run_id, result.records, result.schema_version, src["is_demo"])
        for f in result.failures:
            db.execute("INSERT INTO ingestion_failures (id, run_id, source_key, record_ref, error, payload, created_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (new_id("IGF"), run_id, src["key"], f.get("record_ref"), f.get("error"), f.get("payload"), now_iso()))
        status = "success" if not result.failures else "partial"
        db.execute("UPDATE ingestion_runs SET finished_at = ?, status = ?, records_ingested = ?, records_failed = ?, "
                   "pages = ?, schema_version = ?, bronze_path = ?, cursor_after = ? WHERE id = ?",
                   (now_iso(), status, written["count"], len(result.failures), result.pages, result.schema_version,
                    written["path"], result.next_cursor, run_id))
        db.execute("UPDATE sources SET cursor = ?, last_sync_at = ? WHERE id = ?",
                   (result.next_cursor, now_iso(), src["id"]))
        total = db.fetchone("SELECT COALESCE(SUM(records_ingested), 0) AS n FROM ingestion_runs WHERE source_key = ? "
                            "AND status IN ('success', 'partial')", (src["key"],))["n"]
        register_dataset(db, key=f"bronze_{src['key']}", layer="bronze", scope="corporate", name=f"Bronze · {src['name']}",
                         description="Payloads originais preservados (append-only), com metadados de ingestão.",
                         grain="1 linha por registro recebido por execução", path=f"bronze/{src['key']}/",
                         fmt="jsonl", row_count=int(total), schema={"payload": "json", "_run_id": "string"},
                         schema_version=result.schema_version, is_demo=src["is_demo"])
        record_audit(db, actor, "source.sync", "source", src["id"], {"run_id": run_id, "records": written["count"]})
        return {"run_id": run_id, "status": status, "records": written["count"], "failures": len(result.failures),
                "cursor": result.next_cursor}
    except Exception as exc:  # falhas de ingestão são registradas, nunca silenciadas
        msg = exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {str(exc)[:200]}"
        db.execute("UPDATE ingestion_runs SET finished_at = ?, status = 'failed', error = ? WHERE id = ?",
                   (now_iso(), msg, run_id))
        db.execute("INSERT INTO ingestion_failures (id, run_id, source_key, record_ref, error, created_at) "
                   "VALUES (?, ?, ?, NULL, ?, ?)", (new_id("IGF"), run_id, src["key"], msg, now_iso()))
        record_audit(db, actor, "source.sync_failed", "source", src["id"], {"run_id": run_id, "error": msg})
        log.error("ingestion failed for %s: %s", src["key"], msg)
        return {"run_id": run_id, "status": "failed", "records": 0, "error": msg}


def list_ingestion_runs(db: Database, source_key: Optional[str] = None, limit: int = 100) -> List[dict]:
    limit = max(1, min(int(limit), 500))
    if source_key:
        return db.fetchall(f"SELECT * FROM ingestion_runs WHERE source_key = ? ORDER BY started_at DESC LIMIT {limit}",
                           (source_key,))
    return db.fetchall(f"SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT {limit}")


def apply_features(db: Database) -> Dict[str, Any]:
    """Aplica os recursos opcionais (Configurações › Recursos) aos dados: liga/desliga o setor Estoque."""
    from goops_core.runtime_config import get_section
    from ..sectors import stock
    from ..support import pipeline as support
    feats = get_section(db, "features")
    if feats.get("sector_stock"):
        stock.seed_stock_sector(db)
    stock.set_enabled(db, bool(feats.get("sector_stock")))
    support.set_enabled(db, bool(feats.get("support", True)))
    return feats
