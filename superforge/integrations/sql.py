from __future__ import annotations
import sqlite3
from typing import Iterable
from .base import ERPAdapter,ExternalRecord,PushReceipt

class SQLReportAdapter(ERPAdapter):
    """Read/write adapter for approved report views. SQLite works natively; other DBs can inject a DB-API connector in a custom adapter."""
    def _connect(self):
        driver=(self.config.get("driver") or "sqlite").lower()
        if driver!="sqlite":
            raise RuntimeError("built-in SQLReportAdapter supports sqlite; install a custom DB-API/ODBC adapter for this ERP")
        path=self.config.get("database")
        if not path: raise ValueError("database path required")
        con=sqlite3.connect(path)
        con.row_factory=sqlite3.Row
        return con
    def pull(self,entity_type:str,*,cursor:str="")->Iterable[ExternalRecord]:
        queries=self.config.get("queries") or {}
        query=queries.get(entity_type)
        if not query: raise ValueError(f"no approved read query configured for {entity_type}")
        con=self._connect()
        try:
            rows=con.execute(query).fetchall()
            id_field=self.config.get("external_id_field","id")
            return [ExternalRecord(str(dict(r).get(id_field) or ""),entity_type,dict(r)) for r in rows]
        finally: con.close()
    def push(self,entity_type:str,operation:str,payload:dict)->PushReceipt:
        statements=(self.config.get("write_statements") or {}).get(entity_type,{})
        statement=statements.get(operation)
        if not statement: return PushReceipt(False,message="no approved write statement configured; use outbox/export or a custom adapter")
        con=self._connect()
        try:
            con.execute(statement,payload); con.commit()
            return PushReceipt(True,str(payload.get("id") or ""),"database write committed")
        finally: con.close()
