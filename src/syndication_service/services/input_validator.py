"""Input validation service for query parameters"""
from typing import Dict, Any, Optional
from fastapi import HTTPException


class InputValidator:
    """クエリパラメータのバリデーションとサニタイゼーション"""

    VALID_SPECIES = ["犬", "猫", "その他"]
    VALID_CATEGORY = ["adoption", "lost"]
    VALID_STATUS = ["sheltered", "adopted", "returned", "deceased"]
    VALID_SEX = ["男の子", "女の子", "不明"]
    MAX_QUERY_LENGTH = 1000
    MALICIOUS_PATTERNS = ["<", ">", "script", "SELECT", "DROP", "INSERT", "DELETE", "UPDATE"]

    @staticmethod
    def validate_query_params(params: Dict[str, Any]) -> None:
        """
        クエリパラメータをバリデーション

        Args:
            params: クエリパラメータ辞書

        Raises:
            HTTPException(400): 無効なパラメータ時
        """
        # URL長チェック
        query_str = "&".join(
            f"{k}={v}" for k, v in params.items() if v is not None
        )
        if len(query_str) > InputValidator.MAX_QUERY_LENGTH:
            raise HTTPException(
                status_code=400,
                detail="リクエストURLが長すぎます"
            )

        # 悪意のある文字列検出
        for key, value in params.items():
            if value is not None:
                value_str = str(value)
                for pattern in InputValidator.MALICIOUS_PATTERNS:
                    if pattern in value_str:
                        raise HTTPException(
                            status_code=400,
                            detail=f"無効なパラメータ: {key}"
                        )

        # 有効値チェック
        if params.get("species") and params["species"] not in InputValidator.VALID_SPECIES:
            raise HTTPException(
                status_code=400,
                detail="無効なパラメータ: species"
            )
        if params.get("category") and params["category"] not in InputValidator.VALID_CATEGORY:
            raise HTTPException(
                status_code=400,
                detail="無効なパラメータ: category"
            )
        if params.get("status") and params["status"] not in InputValidator.VALID_STATUS:
            raise HTTPException(
                status_code=400,
                detail="無効なパラメータ: status"
            )
        if params.get("sex") and params["sex"] not in InputValidator.VALID_SEX:
            raise HTTPException(
                status_code=400,
                detail="無効なパラメータ: sex"
            )
