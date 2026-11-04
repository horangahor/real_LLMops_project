# 다른 Windows PC에서 캐시까지 이어가기

이 저장소는 `draft_history/` 전체와 `cache-snapshot.json`을 포함한다. PDF Parse 원본·이미지, A/B 모드 근거 수집·사용자 검토 결정, 작성 계획, 완료한 소절·편집 체크포인트, 실패 후보·응답 캐시·경고 모음도 함께 내려온다. `.env`, 가상환경, Python 바이트코드와 PC별 이관 상태는 포함하지 않는다.

긴 캐시 경로를 받을 수 있도록 기존 체크아웃에서 다음 순서로 실행한다. 새로 복제할 때는 `git -c core.longpaths=true clone <저장소 URL>`을 사용할 수 있다.

```powershell
git config core.longpaths true
git pull
python -m pip install -r requirements.txt
python workspace_cache.py prepare
python -m streamlit run streamlit_app.py
```

API 키는 새 PC의 `.env`에 설정한다. 같은 원본 PDF·골든 가이드·모드·모델 설정을 선택하고 기존 초안 작성을 재개한다. 완료한 동일 입력은 캐시를 재사용하고, 미완료 요청과 변경한 입력만 호출한다. PC 메모리 안에만 있던 Streamlit 세션 상태와 진행 중 HTTP 연결은 이관되지 않는다.

`prepare`는 스냅샷의 파일 체크섬을 확인한 다음 현재 체크아웃 경로에 맞춰 파생 JSON의 절대 경로를 바꾼다. 기존 캐시 식별자·체크포인트의 의미 해시는 원래 작업 경로를 기준으로 유지한다. Parse·Solar의 `.native.json` 응답은 바이트 그대로 보존한다. 파생 JSON 파일의 바이트 해시를 참조하는 마지막 초안 포인터 등은 함께 갱신한다. 현재 경로에서 이미 수정·재개한 파일은 원본으로 덮어쓰지 않는다. Git의 `draft_history/** -text` 설정은 체크아웃 때 줄바꿈을 바꿔 캐시 검증을 깨뜨리지 않도록 한다.

초기 이관 확인만 할 때는 `python workspace_cache.py verify`를 실행한다. `needs_prepare=true`면 아직 경로 변환이 필요한 상태다. 이관 명령은 API를 호출하지 않는다. 로컬 캐시를 수정한 뒤 예전 스냅샷으로 다시 초기화하는 명령이 아니다.

이후 다른 PC에서 새 결과까지 공유할 때도 `python workspace_cache.py snapshot`으로 목록을 갱신한 뒤 변경한 코드·`draft_history/`·`cache-snapshot.json`을 함께 커밋한다. 앱의 작업이 중단·완료돼 파일이 안정된 상태에서 스냅샷을 생성한다. 캐시의 본문과 연구 자료를 포함하므로 저장소 공유 범위에 맞춰 사용한다.
