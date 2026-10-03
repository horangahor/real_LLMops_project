import os
from pathlib import Path
from dotenv import load_dotenv

# .env 환경 변수 로드
load_dotenv()

# Upstage API Key
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")

# Agent 설정 (필요시 사용)

# 방법, 결과 추출 에이전트
METHOD_RESULT_AGENT_ID = os.getenv("METHOD_RESULT_AGENT_ID")
METHOD_RESULT_CONFIG_ID = os.getenv("METHOD_RESULT_CONFIG_ID")

# 논문 구조 파싱 에이전트
STRUCTURE_AGENT_ID = os.getenv("STRUCTURE_AGENT_ID")
STRUCTURE_CONFIG_ID = os.getenv("STRUCTURE_CONFIG_ID")
