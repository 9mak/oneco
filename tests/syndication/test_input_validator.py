"""Tests for InputValidator service"""

import pytest
from fastapi import HTTPException

from src.syndication_service.services.input_validator import InputValidator


class TestInputValidator:
    """Test cases for InputValidator"""

    def test_validate_valid_params(self):
        """有効なパラメータは検証を通過する"""
        params = {
            "species": "犬",
            "category": "adoption",
            "status": "sheltered",
            "sex": "男の子",
            "location": "高知県",
        }
        # Should not raise exception
        InputValidator.validate_query_params(params)

    def test_validate_invalid_species(self):
        """無効な species はエラーを発生"""
        params = {"species": "鳥"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ: species" in str(exc_info.value.detail)

    def test_validate_invalid_category(self):
        """無効な category はエラーを発生"""
        params = {"category": "invalid"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ: category" in str(exc_info.value.detail)

    def test_validate_invalid_status(self):
        """無効な status はエラーを発生"""
        params = {"status": "invalid"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ: status" in str(exc_info.value.detail)

    def test_validate_invalid_sex(self):
        """無効な sex はエラーを発生"""
        params = {"sex": "invalid"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ: sex" in str(exc_info.value.detail)

    def test_validate_query_too_long(self):
        """1000文字を超えるクエリはエラーを発生"""
        params = {"location": "a" * 1001}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "リクエストURLが長すぎます" in str(exc_info.value.detail)

    def test_validate_malicious_xss(self):
        """XSS パターンはエラーを発生"""
        params = {"location": "<script>alert('xss')</script>"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ" in str(exc_info.value.detail)

    def test_validate_malicious_sql(self):
        """SQL injection パターンはエラーを発生"""
        params = {"location": "'; DROP TABLE animals; --"}
        with pytest.raises(HTTPException) as exc_info:
            InputValidator.validate_query_params(params)
        assert exc_info.value.status_code == 400
        assert "無効なパラメータ" in str(exc_info.value.detail)

    def test_validate_none_values_allowed(self):
        """None 値は許可される"""
        params = {"species": None, "category": None, "location": "高知県"}
        # Should not raise exception
        InputValidator.validate_query_params(params)

    def test_validate_empty_params(self):
        """空のパラメータは許可される"""
        params = {}
        # Should not raise exception
        InputValidator.validate_query_params(params)
