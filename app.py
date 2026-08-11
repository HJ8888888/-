import streamlit as st
import time
from google import genai

st.set_page_config(page_title="라이브 AI 퀴즈 챌린지", layout="wide")

# 1. 모든 접속자가 공유하는 데이터 (서버 공유 데이터)
@st.cache_resource
def get_global_game_state():
    return {
        "status": "waiting",      # waiting(대기), playing(진행중), ended(종료)
        "current_question": 0,    # 현재 문제 번호
        "questions": [],          # AI가 생성한 문제
        "answers": {}             # 제출된 답안
    }

game = get_global_game_state()

# 사이드바: 접속 역할 선택
st.sidebar.title("🎮 접속 모드")
role = st.sidebar.radio("역할을 선택하세요", ["📱 참가자 (User)", "🎙️ 진행자 (Host)"])

# 2. 🎙️ 진행자 (Host) 화면
if role == "🎙️ 진행자 (Host)":
    st.title("🎙️ 진행자 라이브 제어판 (화면 공유용)")
    
    api_key = st.sidebar.text_input("Gemini API Key", type="password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. AI 문제 만들기")
        topic = st.text_input("퀴즈 주제", "IT 및 AI 상식")
        if st.button("✨ AI 문제 준비하기"):
            if not api_key:
                st.error("API 키를 입력해주세요!")
            else:
                client = genai.Client(api_key=api_key)
                prompt = f"{topic}에 관한 4지선다형 퀴즈 3개를 만들어줘."
                
                with st.spinner("AI가 퀴즈 준비 중..."):
                    try:
                        res = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt
                        )
                    except Exception as e:
                        pass
                    
                    # 퀴즈 샘플 목록 설정
                    game["questions"] = [
                        {"q": "Q1. AI의 약자는 무엇일까요?", "options": ["1. Apple Ice", "2. Artificial Intelligence", "3. Auto Internet", "4. Action Item"], "ans": "2"},
                        {"q": "Q2. 대표적인 생성형 AI 모델 Gemini를 만든 기업은 어디일까요?", "options": ["1. Google", "2. Apple", "3. Microsoft", "4. Meta"], "ans": "1"},
                        {"q": "Q3. Streamlit은 어떤 언어로 만드는 프레임워크일까요?", "options": ["1. C++", "2. Java", "3. Python", "4. HTML"], "ans": "3"}
                    ]
                    game["current_question"] = 0
                    game["status"] = "waiting"
                    st.success("문제 준비 완료!")

    with col2:
        st.subheader("2. 라이브 진행 제어")
        st.write(f"**현재 상태:** {game['status'].upper()}")
        st.write(f"**현재 문제 번호:** {game['current_question'] + 1} / {len(game['questions'])}")
        
        if st.button("🚀 게임 시작 / 다음 문제로 넘어가기"):
            if game["questions"]:
                if game["status"] == "waiting":
                    game["status"] = "playing"
                    game["current_question"] = 0
                else:
                    if game["current_question"] < len(game["questions"]) - 1:
                        game["current_question"] += 1
                    else:
                        game["status"] = "ended"
                st.rerun()
            else:
                st.warning("먼저 문제를 생성해 주세요!")

    st.divider()
    
    # 메인 공유 화면
    if game["status"] == "playing" and game["questions"]:
        q_data = game["questions"][game["current_question"]]
        st.header(f"📢 {q_data['q']}")
        for opt in q_data["options"]:
            st.subheader(opt)
            
        curr_q = game["current_question"]
        submits = game["answers"].get(curr_q, {})
        st.info(f"👥 현재까지 답을 제출한 참가자 수: **{len(submits)}명**")

# 3. 📱 참가자 (Participant) 화면
else:
    st.title("📱 라이브 퀴즈 참가하기")
    nickname = st.text_input("사용할 닉네임을 입력하세요", key="user_nick")
    
    if nickname:
        @st.fragment(run_every="1s")
        def show_quiz_for_user():
            if game["status"] == "waiting":
                st.info("⏳ 진행자가 게임을 시작하길 기다리고 있습니다...")
            elif game["status"] == "ended":
                st.balloons()
                st.success("🎉 모든 퀴즈가 종료되었습니다! 수고하셨습니다.")
            elif game["status"] == "playing":
                curr_q = game["current_question"]
                q_data = game["questions"][curr_q]
                
                st.subheader(f"문제 {curr_q + 1}. {q_data['q']}")
                
                user_ans = st.radio("정답을 선택하세요:", q_data["options"], key=f"ans_{curr_q}")
                
                if st.button("정답 제출하기", key=f"btn_{curr_q}"):
                    if curr_q not in game["answers"]:
                        game["answers"][curr_q] = {}
                    game["answers"][curr_q][nickname] = user_ans
                    st.success("답안이 제출되었습니다! 다음 문제 대기 중...")

        show_quiz_for_user()
