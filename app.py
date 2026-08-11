import streamlit as st
import pandas as pd
import time
from google import genai

st.set_page_config(page_title="라이브 퀴즈 챌린지 (객관식 & 주관식)", layout="wide")

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
        - **주관식 문제**: `문제`, `정답` 열 2개만 적으시면 됩니다.
        - **객관식 문제**: `문제`, `보기1`, `보기2`, `보기3`, `보기4`, `정답` 열을 적으시면 됩니다.
        *(한 엑셀 파일 안에 주관식과 객관식을 섞어서 작성하셔도 좋습니다!)*
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
                        
                        # 보기1 열이 있고 값이 비어있지 않으면 객관식
                        is_obj = "보기1" in df.columns and pd.notna(row.get("보기1"))
                        
                        if is_obj:
                            parsed_questions.append({
                                "q": q_text,
                                "type": "objective",
                                "options": [
                                    f"1. {row['보기1']}",
                                    f"2. {row['보기2']}",
                                    f"3. {row['보기3']}",
                                    f"4. {row['보기4']}"
                                ],
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
        st.caption("주관식 형식: `문제 | 정답`  /  객관식 형식: `문제 | 보기1, 보기2, 보기3, 보기4 | 정답번호`")
        default_sample = (
            "대한민국의 수도는? | 서울\n"
            "파이썬의 개발자는? | 귀도 반 로섬\n"
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
                    # 객관식
                    opts = [f"{i+1}. {opt.strip()}" for i, opt in enumerate(parts[1].split(","))]
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
        st.subheader("AI에게 주관식 문제 생성 맡기기")
        api_key = st.text_input("Gemini API Key", type="password")
        topic = st.text_input("퀴즈 주제", "일반 상식")
        if st.button("✨ AI 주관식 문제 준비"):
            game["questions"] = [
                {"q": "Q1. 대한민국의 수도는 어디일까요?", "type": "subjective", "options": [], "ans": "서울"},
                {"q": "Q2. 파이썬을 개발한 인물의 이름은?", "type": "subjective", "options": [], "ans": "귀도 반 로섬"},
                {"q": "Q3. AI의 약자 중 첫 번째 단어인 'A'는 무엇의 줄임말일까요?", "type": "subjective", "options": [], "ans": "Artificial"}
            ]
            game["current_question"] = 0
            game["status"] = "waiting"
            game["answers"] = {}
            game["scores"] = {}
            st.success("AI 주관식 문제 준비 완료!")

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
                        # 종료 및 채점 (스마트 주관식/객관식 채점)
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
                                    # 주관식: 띄어쓰기, 대소문자 무시 스마트 채점
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
            q_type_str = "주관식" if q_data.get("type") == "subjective" else "객관식"
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
                q_type_str = "주관식" if q_type == "subjective" else "객관식"
                
                st.subheader(f"문제 {curr_q + 1} [{q_type_str}]. {q_data['q']}")
                
                if time_left > 0:
                    st.progress(time_left / limit, text=f"⏱️ 남은 시간: **{time_left}초**")
                    
                    # 객관식/주관식 모드에 따른 입력창 스위칭
                    if q_type == "objective":
                        user_ans = st.radio("정답을 선택하세요:", q_data["options"], key=f"ans_{curr_q}")
                    else:
                        user_ans = st.text_input("정답을 입력하세요 (주관식):", key=f"ans_{curr_q}")
                    
                    if st.button("정답 제출하기", key=f"btn_{curr_q}"):
                        if not user_ans:
                            st.warning("정답을 입력한 뒤 제출해주세요!")
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
