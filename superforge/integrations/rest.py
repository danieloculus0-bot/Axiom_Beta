from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable
from .base import ERPAdapter,ExternalRecord,PushReceipt

class RESTAdapter(ERPAdapter):
    def _request(self,method:str,path:str,body:dict|None=None):
        base=str(self.config.get("base_url","")).rstrip("/")
        if not base: raise ValueError("base_url is required")
        headers={"Accept":"application/json","Content-Type":"application/json"}
        token=self.credentials.get("token") or self.credentials.get("bearer_token")
        if token: headers["Authorization"]=f"Bearer {token}"
        headers.update(self.config.get("headers") or {})
        req=urllib.request.Request(base+"/"+path.lstrip("/"),method=method,headers=headers,data=(json.dumps(body).encode("utf-8") if body is not None else None))
        try:
            with urllib.request.urlopen(req,timeout=float(self.config.get("timeout",30))) as response:
                raw=response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail=exc.read().decode("utf-8",errors="replace")[:2000]
            raise RuntimeError(f"ERP HTTP {exc.code}: {detail}") from exc
    def pull(self,entity_type:str,*,cursor:str="")->Iterable[ExternalRecord]:
        endpoints=self.config.get("endpoints") or {}
        path=endpoints.get(entity_type) or endpoints.get("default")
        if not path: raise ValueError(f"no REST endpoint configured for {entity_type}")
        if cursor: path=path+("&" if "?" in path else "?")+urllib.parse.urlencode({"cursor":cursor})
        data=self._request("GET",path)
        rows=data if isinstance(data,list) else data.get(self.config.get("records_key","records"),[])
        id_field=self.config.get("external_id_field","id")
        return [ExternalRecord(str(row.get(id_field) or ""),entity_type,dict(row)) for row in rows]
    def push(self,entity_type:str,operation:str,payload:dict)->PushReceipt:
        endpoints=self.config.get("write_endpoints") or self.config.get("endpoints") or {}
        path=endpoints.get(entity_type) or endpoints.get("default")
        if not path: return PushReceipt(False,message=f"no write endpoint configured for {entity_type}")
        method={"create":"POST","update":"PUT","delete":"DELETE"}.get(operation.lower(),"POST")
        data=self._request(method,path,payload)
        id_field=self.config.get("external_id_field","id")
        external_id=str(data.get(id_field) or payload.get(id_field) or "")
        return PushReceipt(True,external_id,"sent",data if isinstance(data,dict) else {"response":data})
