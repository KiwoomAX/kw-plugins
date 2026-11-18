"""대시보드 템플릿이 기능을 붙이는 진입점. feature_loader 가 이 모듈의 router 를 /api/<기능 이름> 아래에 붙인다."""
from . import create_router

router = create_router()
