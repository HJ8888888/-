import streamlit as st
import pandas as pd
import time
from google import genai

st.set_page_config(page_title="라이브 엑셀 & AI 퀴즈 챌린지", layout="wide")

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
        "q_start_time": 0          # 문제 시작 시각
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
        st.info("💡 엑셀 첫 번째 행(열 이름)은 반드시 `문제`, `보기1`, `보기2`, `보기3`, `보기4`, `정답` 으로 작성해 주세요! (정답은 1~4 숫자)")
        
        uploaded_file = st.file_uploader("엑셀 또는 CSV 파일을 선택하세요", type=["xlsx", "csv"])
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.write("📋 미리보기:", df.head())
                
                if st.button("📊 이 엑셀 파일로 문제 등록하기"):
                    parsed_questions = []
                    for _, row in df.iterrows():
                        parsed_questions.append({
                            "q": str(row["문제"]),
                            "options": [
                                f"1. {row['보기1']}",
                                f"2. {row['보기2']}",
                                f"3. {row['보기3']}",
                                f"4. {row['보기4']}"
                            ],
                            "ans": str(int(row["정답"]))
                        })
                    
                    game["questions"] = parsed_questions
                    game["current_question"] = 0
                    game["status"] = "waiting"
                    game["answers"] = {}
                    game["scores"] = {}
                    st.success(f"🎉 총 {len(parsed_questions)}개의 엑셀 문제가 준비되었습니다!")
            except Exception as e:
                st.error(f"파일을 읽는 중 오류가 발생했습니다. 열 이름을 확인해주세요! ({e})")

    # --- 탭 2: 직접 입력 ---
    with tab2:
        st.subheader("내가 원하는 문제 직접 입력")
        default_sample = "대한민국의 수도는? | 부산, 인천, 서울, 대구 | 3"
        q_text = st.text_area("문제 | 보기1, 보기2, 보기3, 보기4 | 정답번호", value=default_sample, height=100)
        
        if st.button("📝 텍스트 문제 등록하기"):
            parsed_questions = []
            for line in q_text.strip().split("\n"):
                parts = line.split("|")
                if len(parts) == 3:
                    opts = [f"{i+1}. {opt.strip()}" for i, opt in enumerate(parts[1].split(","))]
                    parsed_questions.append({"q": parts[0].strip(), "options": opts, "ans": parts[2].strip()})
            if parsed_questions:
                game["questions"] = parsed_questions
                game["current_question"] = 0
                game["status"] = "waiting"
                game["answers"] = {}
                game["scores"] = {}
                st.success("문제 등록 완료!")

    # --- 탭 3: AI 생성 ---
    with tab3:
        st.subheader("AI에게 문제 생성 맡기기")
        api_key = st.text_input("Gemini API Key", type="password")
        topic = st.text_input("퀴즈 주제", "일반 상식")
        if st.button("✨ AI 문제 준비"):
            game["questions"] = [
                {"q": "Q1. AI의 약자는 무엇일까요?", "options": ["1. Apple Ice", "2. Artificial Intelligence", "3. Auto Internet", "4. Action Item"], "ans": "2"},
                {"q": "Q2. 대표적인 생성형 AI 모델 Gemini를 만든 기업은?", "options": ["1. Google", "2. Apple", "3. Microsoft", "4. Meta"], "ans": "1"}
            ]
            game["current_question"] = 0
            game["status"] = "waiting"
            game["answers"] = {}
            game["scores"] = {}
            st.success("AI 문제 준비 완료!")

    st.divider()

    # --- 진행 제어 ---
    st.subheader("🚀 라이브 진행 제어")
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
                        correct_ans_num = q_data["ans"]
                        for nick, selected_option in user_ans_dict.items():
                            if selected_option.startswith(correct_ans_num):
                                scores[nick] = scores.get(nick, 0) + 1
                            else:
                                scores[nick] = scores.get(nick, 0)
                    game["scores"] = scores
            
            # 문제 시작 타이머 시각 저장
            game["q_start_time"] = time.time()
            st.rerun()

    # --- 현재 진행 화면 ---
    if game["status"] == "playing" and game["questions"]:
        st.divider()
        q_data = game["questions"][game["current_question"]]
        st.header(f"📢 Q{game['current_question']+1}. {q_data['q']}")
        for opt in q_data["options"]:
            st.subheader(f"  {opt}")
        
        curr_q = game["current_question"]
        submits = game["answers"].get(curr_q, {})
        st.info(f"👥 현재 정답 제출인원: **{len(submits)}명**")

    elif game["status"] == "ended":
        st.divider()
        st.header("🏆 최종 결과 TOP 5 리더보드")
        if game["scores"]:
            sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
            for rank, (nick, score) in enumerate(sorted_scores, 1):
                icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                st.subheader(f"{icon} **{rank}위**: {nick} — {score}점 / {len(game['questions'])}점 만점")

# ---------------------------------------------------------
# 📱 참가자 (Participant) 화면
# ---------------------------------------------------------
else:
    st.title("📱 라이브 퀴즈 참가하기")
    nickname = st.text_input("사용할 닉네임을 입력하세요", key="user_nick")
    
    if nickname:
        @st.fragment(run_every="1s")
        def show_quiz_for_user():
            if game["status"] == "waiting":
                st.info("⏳ 진행자가 게임을 시작하길 기다리고 있습니다...")
            
            elif game["status"] == "playing":
                curr_q = game["current_question"]
                q_data = game["questions"][curr_q]
                
                # 타이머 계산
                elapsed = time.time() - game.get("q_start_time", time.time())
                limit = game.get("timer_sec", 15)
                time_left = max(0, int(limit - elapsed))
                
                st.subheader(f"문제 {curr_q + 1}. {q_data['q']}")
                
                # 실시간 남은 시간 타이머 바
                if time_left > 0:
                    st.progress(time_left / limit, text=f"⏱️ 남은 시간: **{time_left}초**")
                    user_ans = st.radio("정답을 선택하세요:", q_data["options"], key=f"ans_{curr_q}")
                    
                    if st.button("정답 제출하기", key=f"btn_{curr_q}"):
                        if curr_q not in game["answers"]:
                            game["answers"][curr_q] = {}
                        game["answers"][curr_q][nickname] = user_ans
                        st.success("답안 제출 완료! 시간 종료 또는 다음 문제를 기다려주세요.")
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
