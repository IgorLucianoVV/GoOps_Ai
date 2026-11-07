"""Fábrica de conectores a partir do registro de fontes."""
from __future__ import annotations

from typing import Any, Dict

from goops_core.errors import ValidationError

from .base import BaseConnector
from .demo_connector import DemoConnector
from .file_connector import FileConnector
from .gocase_complement_connector import GocaseComplementConnector
from .http_connector import HttpJsonConnector
from .support_demo_connector import SupportDemoConnector

CONNECTORS = {"demo": DemoConnector, "http_json": HttpJsonConnector, "file": FileConnector,
              "gocase_complement": GocaseComplementConnector, "support_demo": SupportDemoConnector}


def build_connector(source_key: str, connector: str, config: Dict[str, Any]) -> BaseConnector:
    cls = CONNECTORS.get(connector)
    if cls is None:
        raise ValidationError(f"Conector desconhecido: {connector}. Disponíveis: {', '.join(CONNECTORS)}")
    return cls(source_key, config)
