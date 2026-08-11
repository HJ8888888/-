import streamlit as st
import pandas as pd
import time
from google import genai

st.set_page_config(page_title="라이브 퀴즈 챌린지", layout="wide")

# 1. 전역 게임 상태 공유 (서버 저장소)
@st.cache_resource
def get_global_game_state():
    return {
        "status": "waiting",      # waiting(대기), playing(진행중), ended(종료)
        "current_question": 0,    # 현재 문제 번호
        "questions": [],          # 문제 목록
        "answers": {},             # 제출 답안
        "scores": {},              # 참가자 점수
        "timer_sec": 15,           # 문제당 제한 시간 (초)
        "q_start_time": 0,         # 문제 시작 시각
        "participants": []         # 👥 접속한 참가자 명단
    }

game = get_global_game_state()

st.sidebar.title("🎮 접속 모드")
role = st.sidebar.radio("역할을 선택하세요", ["📱 참가자 (User)", "🎙️ 진행자 (Host)"])

# ---------------------------------------------------------
# 🎙️ 진행자 (Host) 화면
# ---------------------------------------------------------
if role == "🎙️ 진행자 (Host)":
    st.title("🎙️ 진행자 라이브 제어판")
    
    # 제한 시간 설정
    game["timer_sec"] = st.number_input("⏱️ 문제당 제한 시간(초)을 설정하세요:", min_value=5, max_value=120, value=15, step=5)
    
    tab1, tab2, tab3 = st.tabs(["📊 엑셀/CSV 업로드", "✍️ 직접 입력", "✨ AI 자동 생성"])
    
    # --- 탭 1: 엑셀 파일 업로드 ---
    with tab1:
        st.subheader("📁 엑셀(.xlsx) 파일로 문제 등록")
        st.info("""
        💡 **엑셀 작성 팁**
        - **OX / 2지 선다 문제**: `보기1`, `보기2`만 입력하고 `보기3`, `보기4`를 **빈칸**으로 남겨두시면 3, 4번 보기는 보이지 않습니다!
        - **주관식 문제**: `문제`, `정답` 열 2개만 입력하시면 됩니다.
        - **4지 선다**: `보기1`~`보기4` 모두 채워주시면 됩니다.
        """)
        
        uploaded_file = st.file_uploader("엑셀 또는 CSV 파일 선택", type=["xlsx", "csv"])
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                st.write("📋 미리보기:", df.head())
                
                if st.button("📊 이 엑셀 파일로 문제 등록하기"):
                    parsed_questions = []
                    for _, row in df.iterrows():
                        q_text = str(row["문제"]).strip()
                        ans_text = str(row["정답"]).strip()
                        
                        # 보기1 열이 있고 빈칸이 아니면 객관식/OX
                        is_obj = "보기1" in df.columns and pd.notna(row.get("보기1")) and str(row.get("보기1")).strip() != ""
                        
                        if is_obj:
                            # 빈칸이 아닌 보기만 동적으로 추려서 리스트 생성 (3, 4번 빈칸 자동제거)
                            options = []
                            for idx in range(1, 5):
                                col_name = f"보기{idx}"
                                if col_name in df.columns and pd.notna(row.get(col_name)):
                                    val = str(row[col_name]).strip()
                                    if val and val.lower() != 'nan':
                                        options.append(f"{idx}. {val}")
                            
                            parsed_questions.append({
                                "q": q_text,
                                "type": "objective",
                                "options": options,
                                "ans": str(int(float(ans_text))) if ans_text.isdigit() or ans_text.replace('.','',1).isdigit() else ans_text
                            })
                        else:
                            parsed_questions.append({
                                "q": q_text,
                                "type": "subjective",
                                "options": [],
                                "ans": ans_text
                            })
                    
                    game["questions"] = parsed_questions
                    game["current_question"] = 0
                    game["status"] = "waiting"
                    game["answers"] = {}
                    game["scores"] = {}
                    st.success(f"🎉 총 {len(parsed_questions)}개의 문제가 준비되었습니다!")
            except Exception as e:
                st.error(f"오류가 발생했습니다. 열 이름을 확인해주세요! ({e})")

    # --- 탭 2: 직접 입력 ---
    with tab2:
        st.subheader("내가 원하는 문제 직접 입력")
        st.caption("OX 형식: `문제 | O, X | 정답번호(1 또는 2)`  /  4지선다: `문제 | 보기1, 보기2, 보기3, 보기4 | 정답번호`")
        default_sample = (
            "파이썬은 초보자가 배우기 쉬운 프로그래밍 언어이다. | O, X | 1\n"
            "대한민국의 수도는? | 서울\n"
            "AI의 약자는? | Apple Ice, Artificial Intelligence, Auto Internet, Action Item | 2"
        )
        q_text = st.text_area("문제 입력:", value=default_sample, height=120)
        
        if st.button("📝 텍스트 문제 등록하기"):
            parsed_questions = []
            for line in q_text.strip().split("\n"):
                parts = line.split("|")
                if len(parts) == 2:
                    # 주관식
                    parsed_questions.append({
                        "q": parts[0].strip(),
                        "type": "subjective",
                        "options": [],
                        "ans": parts[1].strip()
                    })
                elif len(parts) == 3:
                    # 객관식 / OX
                    raw_opts = [opt.strip() for opt in parts[1].split(",") if opt.strip()]
                    opts = [f"{i+1}. {opt}" for i, opt in enumerate(raw_opts)]
                    parsed_questions.append({
                        "q": parts[0].strip(),
                        "type": "objective",
                        "options": opts,
                        "ans": parts[2].strip()
                    })
            if parsed_questions:
                game["questions"] = parsed_questions
                game["current_question"] = 0
                game["status"] = "waiting"
                game["answers"] = {}
                game["scores"] = {}
                st.success("문제 등록 완료!")

    # --- 탭 3: AI 생성 ---
    with tab3:
        st.subheader("AI에게 OX 문제 생성 맡기기")
        api_key = st.text_input("Gemini API Key", type="password")
        topic = st.text_input("퀴즈 주제", "일반 상식")
        if st.button("✨ AI OX 문제 준비"):
            game["questions"] = [
                {"q": "Q1. 파이썬은 C언어보다 나중에 개발된 언어이다.", "type": "objective", "options": ["1. O", "2. X"], "ans": "1"},
                {"q": "Q2. 물의 화학식은 H2O이다.", "type": "objective", "options": ["1. O", "2. X"], "ans": "1"},
                {"q": "Q3. 태양계에서 가장 큰 행성은 지구이다.", "type": "objective", "options": ["1. O", "2. X"], "ans": "2"}
            ]
            game["current_question"] = 0
            game["status"] = "waiting"
            game["answers"] = {}
            game["scores"] = {}
            st.success("AI OX 문제 준비 완료!")

    st.divider()

    # --- 실시간 진행 제어 ---
    @st.fragment(run_every="2s")
    def show_host_dashboard():
        st.subheader("🚀 라이브 진행 제어")
        p_count = len(game["participants"])
        st.info(f"👥 **현재 입장한 참가자 ({p_count}명):** " + (", ".join([f"`{p}`" for p in game["participants"]]) if game["participants"] else "아직 입장한 참가자가 없습니다."))
        
        if st.button("▶️ 게임 시작 / 다음 문제 넘어가기"):
            if not game["questions"]:
                st.warning("먼저 문제를 등록해 주세요!")
            else:
                if game["status"] == "waiting":
                    game["status"] = "playing"
                    game["current_question"] = 0
                elif game["status"] == "playing":
                    if game["current_question"] < len(game["questions"]) - 1:
                        game["current_question"] += 1
                    else:
                        # 종료 및 채점
                        game["status"] = "ended"
                        scores = {}
                        for q_idx, q_data in enumerate(game["questions"]):
                            user_ans_dict = game["answers"].get(q_idx, {})
                            correct_ans = str(q_data["ans"]).strip()
                            q_type = q_data.get("type", "objective")
                            
                            for nick, user_ans in user_ans_dict.items():
                                user_ans_clean = str(user_ans).strip()
                                if q_type == "objective":
                                    if user_ans_clean.startswith(correct_ans):
                                        scores[nick] = scores.get(nick, 0) + 1
                                    else:
                                        scores[nick] = scores.get(nick, 0)
                                else:
                                    # 주관식 스마트 채점
                                    norm_user = user_ans_clean.replace(" ", "").lower()
                                    norm_corr = correct_ans.replace(" ", "").lower()
                                    if norm_user == norm_corr:
                                        scores[nick] = scores.get(nick, 0) + 1
                                    else:
                                        scores[nick] = scores.get(nick, 0)
                        game["scores"] = scores
                
                game["q_start_time"] = time.time()
                st.rerun()

        # --- 현재 문제 화면 ---
        if game["status"] == "playing" and game["questions"]:
            st.divider()
            q_data = game["questions"][game["current_question"]]
            q_type_str = "주관식" if q_data.get("type") == "subjective" else "객관식/OX"
            st.header(f"📢 Q{game['current_question']+1} [{q_type_str}]. {q_data['q']}")
            
            if q_data.get("type") == "objective":
                for opt in q_data["options"]:
                    st.subheader(f"  {opt}")
            else:
                st.info(f"💡 정답: `{q_data['ans']}` (진행자 전용 정답 확인)")
            
            curr_q = game["current_question"]
            submits = game["answers"].get(curr_q, {})
            st.success(f"✍️ 정답 제출 완료 인원: **{len(submits)}명 / {p_count}명**")

        elif game["status"] == "ended":
            st.divider()
            st.header("🏆 최종 결과 TOP 5 리더보드")
            if game["scores"]:
                sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
                for rank, (nick, score) in enumerate(sorted_scores, 1):
                    icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                    st.subheader(f"{icon} **{rank}위**: {nick} — {score}점 / {len(game['questions'])}점 만점")

    show_host_dashboard()

# ---------------------------------------------------------
# 📱 참가자 (Participant) 화면
# ---------------------------------------------------------
else:
    st.title("📱 라이브 퀴즈 참가하기")
    nickname = st.text_input("사용할 닉네임을 입력하세요", key="user_nick")
    
    if nickname:
        if nickname not in game["participants"]:
            game["participants"].append(nickname)
            
        @st.fragment(run_every="1s")
        def show_quiz_for_user():
            if game["status"] == "waiting":
                st.info(f"⏳ **{nickname}**님 환영합니다! 진행자가 게임을 시작하길 기다리고 있습니다...")
            
            elif game["status"] == "playing":
                curr_q = game["current_question"]
                q_data = game["questions"][curr_q]
                
                elapsed = time.time() - game.get("q_start_time", time.time())
                limit = game.get("timer_sec", 15)
                time_left = max(0, int(limit - elapsed))
                
                q_type = q_data.get("type", "objective")
                q_type_str = "주관식" if q_type == "subjective" else "객관식/OX"
                
                st.subheader(f"문제 {curr_q + 1} [{q_type_str}]. {q_data['q']}")
                
                if time_left > 0:
                    st.progress(time_left / limit, text=f"⏱️ 남은 시간: **{time_left}초**")
                    
                    if q_type == "objective":
                        user_ans = st.radio("정답을 선택하세요:", q_data["options"], key=f"ans_{curr_q}")
                    else:
                        user_ans = st.text_input("정답을 입력하세요 (주관식):", key=f"ans_{curr_q}")
                    
                    if st.button("정답 제출하기", key=f"btn_{curr_q}"):
                        if not user_ans:
                            st.warning("정답을 입력/선택한 뒤 제출해주세요!")
                        else:
                            if curr_q not in game["answers"]:
                                game["answers"][curr_q] = {}
                            game["answers"][curr_q][nickname] = user_ans
                            st.success("답안 제출 완료! 다음 문제를 기다려주세요.")
                else:
                    st.error("⏰ 제한 시간이 종료되었습니다! 더 이상 답안을 제출할 수 없습니다.")
            
            elif game["status"] == "ended":
                st.balloons()
                st.success("🎉 모든 퀴즈가 종료되었습니다!")
                st.divider()
                st.subheader("🏆 최종 순위 (TOP 5)")
                if game["scores"]:
                    sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
                    for rank, (nick, score) in enumerate(sorted_scores, 1):
                        icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                        st.write(f"{icon} **{rank}위**: {nick} ({score}점)")
                    st.divider()
                    my_score = game["scores"].get(nickname, 0)
                    st.info(f"🙋‍♂️ **{nickname}**님의 최종 점수: **{my_score}개** 맞추셨습니다!")

        show_quiz_for_user()
