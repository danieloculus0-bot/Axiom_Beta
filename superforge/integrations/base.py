from __future__ import annotations
from abc import ABC,abstractmethod
from dataclasses import dataclass
from typing import Any,Iterable

@dataclass
class ExternalRecord:
    external_id:str
    entity_type:str
    payload:dict[str,Any]

@dataclass
class PushReceipt:
    ok:bool
    external_id:str=""
    message:str=""
    raw:dict[str,Any]|None=None

class ERPAdapter(ABC):
    """Contract for JobBOSS2, Epicor, Plex, SAP, Infor, custom ERP, or report feeds."""
    def __init__(self,config:dict[str,Any],credentials:dict[str,Any]|None=None):
        self.config=config
        self.credentials=credentials or {}
    @abstractmethod
    def pull(self,entity_type:str,*,cursor:str="")->Iterable[ExternalRecord]: ...
    @abstractmethod
    def push(self,entity_type:str,operation:str,payload:dict[str,Any])->PushReceipt: ...
    def health(self)->dict[str,Any]:
        return {"ok":True,"adapter":self.__class__.__name__}
