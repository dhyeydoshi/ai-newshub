from zxcvbn import zxcvbn
import re
from typing import Dict, List
from config import settings


class PasswordValidator:
    """Password strength validator"""

    @staticmethod
    def validate_password_strength(password: str, user_inputs: List[str] = None) -> Dict:
        # Basic length check
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return {
                "valid": False,
                "score": 0,
                "feedback": f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long",
                "suggestions": [f"Use at least {settings.PASSWORD_MIN_LENGTH} characters"]
            }

        # Check character requirements
        errors = []
        if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("at least one uppercase letter")

        if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("at least one lowercase letter")

        if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r'\d', password):
            errors.append("at least one digit")

        if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
            errors.append("at least one special character")

        if errors:
            return {
                "valid": False,
                "score": 0,
                "feedback": f"Password must contain {', '.join(errors)}",
                "suggestions": [f"Add {error}" for error in errors]
            }

        # Use zxcvbn for strength analysis
        result = zxcvbn(password, user_inputs=user_inputs or [])

        # Require minimum score of 3 (out of 4)
        min_score = 3
        is_valid = result['score'] >= min_score

        feedback_msg = result['feedback'].get('warning', '')
        suggestions = result['feedback'].get('suggestions', [])

        if not is_valid:
            if not feedback_msg:
                feedback_msg = "Password is too weak"
            if not suggestions:
                suggestions = [
                    "Use a longer password",
                    "Add more unique characters",
                    "Avoid common patterns"
                ]

        return {
            "valid": is_valid,
            "score": result['score'],
            "feedback": feedback_msg,
            "suggestions": suggestions,
            "crack_time": result.get('crack_times_display', {}).get('offline_slow_hashing_1e4_per_second', 'unknown')
        }


# Global validator instance
password_validator = PasswordValidator()

