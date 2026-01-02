"""
Supabase REST client - uses httpx directly to avoid SDK key validation issues.
Copied from apify-api/api-backend/services/supabase_client.py
"""

import os
import httpx
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")


class SupabaseTable:
    """Simple table query builder."""
    
    def __init__(self, client: "SupabaseClient", table_name: str):
        self.client = client
        self.table_name = table_name
        self._select_columns = "*"
        self._filters = []
        self._order_by = None
        self._order_desc = False
        self._limit = None
        self._offset = None
    
    def select(self, columns: str = "*") -> "SupabaseTable":
        self._select_columns = columns
        return self
    
    def eq(self, column: str, value: Any) -> "SupabaseTable":
        self._filters.append(f"{column}=eq.{value}")
        return self
    
    def order(self, column: str, desc: bool = False) -> "SupabaseTable":
        self._order_by = column
        self._order_desc = desc
        return self
    
    def range(self, start: int, end: int) -> "SupabaseTable":
        self._offset = start
        self._limit = end - start + 1
        return self
    
    def limit(self, count: int) -> "SupabaseTable":
        self._limit = count
        return self
    
    def neq(self, column: str, value: Any) -> "SupabaseTable":
        self._filters.append(f"{column}=neq.{value}")
        return self
    
    def is_(self, column: str, value: str) -> "SupabaseTable":
        """IS filter for null/true/false checks."""
        self._filters.append(f"{column}=is.{value}")
        return self
    
    def in_(self, column: str, values: List[Any]) -> "SupabaseTable":
        """Filter where column value is in the given list."""
        values_str = ",".join(str(v) for v in values)
        self._filters.append(f"{column}=in.({values_str})")
        return self
    
    def ilike(self, column: str, pattern: str) -> "SupabaseTable":
        """Case-insensitive LIKE filter."""
        self._filters.append(f"{column}=ilike.{pattern}")
        return self
    
    def gte(self, column: str, value: Any) -> "SupabaseTable":
        """Greater than or equal filter."""
        self._filters.append(f"{column}=gte.{value}")
        return self
    
    def lte(self, column: str, value: Any) -> "SupabaseTable":
        """Less than or equal filter."""
        self._filters.append(f"{column}=lte.{value}")
        return self
    
    def lt(self, column: str, value: Any) -> "SupabaseTable":
        """Less than filter."""
        self._filters.append(f"{column}=lt.{value}")
        return self
    
    def _build_url(self) -> str:
        url = f"{self.client.rest_url}/{self.table_name}"
        params = [f"select={self._select_columns}"]
        params.extend(self._filters)
        
        if self._order_by:
            direction = ".desc" if self._order_desc else ".asc"
            params.append(f"order={self._order_by}{direction}")
        
        if self._limit:
            params.append(f"limit={self._limit}")
        if self._offset:
            params.append(f"offset={self._offset}")
        
        return f"{url}?{'&'.join(params)}"
    
    def insert(self, data: Dict[str, Any]) -> "SupabaseTable":
        self._insert_data = data
        self._operation = "insert"
        return self
    
    def upsert(self, data: Dict[str, Any], on_conflict: str = None) -> "SupabaseTable":
        self._upsert_data = data
        self._upsert_conflict = on_conflict
        self._operation = "upsert"
        return self
    
    def update(self, data: Dict[str, Any]) -> "SupabaseTable":
        self._update_data = data
        self._operation = "update"
        return self
    
    def delete(self) -> "SupabaseTable":
        self._operation = "delete"
        return self
    
    def execute(self) -> "SupabaseResponse":
        url = f"{self.client.rest_url}/{self.table_name}"
        
        # INSERT operation
        if hasattr(self, '_operation') and self._operation == "insert":
            response = self.client._request("POST", url, json=self._insert_data)
            return SupabaseResponse(response)
        
        # UPSERT operation
        if hasattr(self, '_operation') and self._operation == "upsert":
            headers = {"Prefer": "resolution=merge-duplicates"}
            if self._upsert_conflict:
                url = f"{url}?on_conflict={self._upsert_conflict}"
            response = self.client._request("POST", url, json=self._upsert_data, extra_headers=headers)
            return SupabaseResponse(response)
        
        # UPDATE operation
        if hasattr(self, '_operation') and self._operation == "update":
            params = []
            params.extend(self._filters)
            if params:
                url = f"{url}?{'&'.join(params)}"
            response = self.client._request("PATCH", url, json=self._update_data)
            return SupabaseResponse(response)
        
        # DELETE operation
        if hasattr(self, '_operation') and self._operation == "delete":
            params = []
            params.extend(self._filters)
            if params:
                url = f"{url}?{'&'.join(params)}"
            response = self.client._request("DELETE", url)
            return SupabaseResponse(response)
        
        # SELECT operation (default)
        url = self._build_url()
        response = self.client._request("GET", url)
        return SupabaseResponse(response)


class SupabaseResponse:
    """Response wrapper."""
    
    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        try:
            self.data = response.json() if response.text else []
        except:
            self.data = []
        
        # Ensure data is always a list for consistency
        if isinstance(self.data, dict):
            self.data = [self.data]


class SupabaseClient:
    """Simple Supabase REST client."""
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self.rest_url = f"{self.url}/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self._client = httpx.Client(timeout=30.0)
    
    def _request(
        self, 
        method: str, 
        url: str, 
        json: Dict = None,
        extra_headers: Dict = None
    ) -> httpx.Response:
        headers = {**self.headers}
        if extra_headers:
            headers.update(extra_headers)
        
        response = self._client.request(method, url, json=json, headers=headers)
        if response.status_code >= 400:
            print(f"[Supabase Error] {method} {url}")
            print(f"[Supabase Error] Status: {response.status_code}")
            print(f"[Supabase Error] Response: {response.text[:500]}")
        response.raise_for_status()
        return response
    
    def table(self, table_name: str) -> SupabaseTable:
        return SupabaseTable(self, table_name)
    
    def rpc(self, function_name: str, params: Dict[str, Any] = None) -> "SupabaseRPC":
        """Call a Postgres function via RPC."""
        return SupabaseRPC(self, function_name, params or {})


class SupabaseRPC:
    """RPC call builder for Postgres functions."""
    
    def __init__(self, client: SupabaseClient, function_name: str, params: Dict[str, Any]):
        self.client = client
        self.function_name = function_name
        self.params = params
    
    def execute(self) -> SupabaseResponse:
        url = f"{self.client.url}/rest/v1/rpc/{self.function_name}"
        response = self.client._request("POST", url, json=self.params)
        return SupabaseResponse(response)


# Create the client instance
supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)


def test_connection() -> bool:
    """Test if Supabase connection works."""
    try:
        result = supabase.table("clients").select("id").limit(1).execute()
        return True
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False
