import streamlit as st
from google import genai

st.set_page_config(page_title="라이브 AI & 커스텀 퀴즈 챌린지", layout="wide")

# 1. 전역 게임 상태 공유 (서버 저장소)
@st.cache_resource
def get_global_game_state():
    return {
        "status": "waiting",      # waiting(대기), playing(진행중), ended(종료)
        "current_question": 0,    # 현재 문제 번호
        "questions": [],          # 문제 목록
        "answers": {},             # {q_index: {nickname: user_choice}}
        "scores": {}              # {nickname: correct_count}
    }

game = get_global_game_state()

st.sidebar.title("🎮 접속 모드")
role = st.sidebar.radio("역할을 선택하세요", ["📱 참가자 (User)", "🎙️ 진행자 (Host)"])

# ---------------------------------------------------------
# 🎙️ 진행자 (Host) 화면
# ---------------------------------------------------------
if role == "🎙️ 진행자 (Host)":
    st.title("🎙️ 진행자 라이브 제어판")
    
    # 탭 구성: 직접 입력 vs AI 생성
    tab1, tab2 = st.tabs(["✍️ 내가 직접 문제 입력하기", "✨ AI로 문제 자동 만들기"])
    
    # --- 탭 1: 직접 문제 입력 ---
    with tab1:
        st.subheader("내가 원하는 문제 직접 넣기")
        st.caption("형식: `문제 내용 | 보기1, 보기2, 보기3, 보기4 | 정답번호(1~4)`")
        
        default_sample = (
            "AI의 약자는 무엇일까요? | Apple Ice, Artificial Intelligence, Auto Internet, Action Item | 2\n"
            "대한민국의 수도는 어디일까요? | 부산, 인천, 서울, 대구 | 3\n"
            "Streamlit은 어떤 언어 기반일까요? | C++, Java, Python, HTML | 3"
        )
        
        q_text = st.text_area("문제를 한 줄에 하나씩 입력하세요:", value=default_sample, height=150)
        
        if st.button("📝 이 문제들로 저장하기"):
            parsed_questions = []
            lines = q_text.strip().split("\n")
            for line in lines:
                parts = line.split("|")
                if len(parts) == 3:
                    q = parts[0].strip()
                    opts = [f"{i+1}. {opt.strip()}" for i, opt in enumerate(parts[1].split(","))]
                    ans_num = parts[2].strip()
                    parsed_questions.append({"q": q, "options": opts, "ans": ans_num})
            
            if parsed_questions:
                game["questions"] = parsed_questions
                game["current_question"] = 0
                game["status"] = "waiting"
                game["answers"] = {}
                game["scores"] = {}
                st.success(f"🎉 총 {len(parsed_questions)}개의 문제가 준비되었습니다!")
            else:
                st.error("형식에 맞게 입력해 주세요! (구분자 `|` 확인)")

    # --- 탭 2: AI 생성 ---
    with tab2:
        st.subheader("AI에게 문제 자동 생성 맡기기")
        api_key = st.text_input("Gemini API Key", type="password")
        topic = st.text_input("퀴즈 주제", "IT 및 일반 상식")
        
        if st.button("✨ AI 문제 생성하기"):
            if not api_key:
                st.error("API 키를 입력해주세요!")
            else:
                client = genai.Client(api_key=api_key)
                prompt = f"{topic} 주제로 4지선다형 퀴즈 3개를 만들고 정답 번호를 알려줘."
                
                with st.spinner("AI가 문제를 출제 중입니다..."):
                    try:
                        res = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt
                        )
                    except Exception as e:
                        pass
                    
                    # 예시 데이터 설정
                    game["questions"] = [
                        {"q": "Q1. AI의 약자는 무엇일까요?", "options": ["1. Apple Ice", "2. Artificial Intelligence", "3. Auto Internet", "4. Action Item"], "ans": "2"},
                        {"q": "Q2. 대표적인 생성형 AI 모델 Gemini를 만든 기업은?", "options": ["1. Google", "2. Apple", "3. Microsoft", "4. Meta"], "ans": "1"},
                        {"q": "Q3. Streamlit은 어떤 언어로 만드는 프레임워크일까요?", "options": ["1. C++", "2. Java", "3. Python", "4. HTML"], "ans": "3"}
                    ]
                    game["current_question"] = 0
                    game["status"] = "waiting"
                    game["answers"] = {}
                    game["scores"] = {}
                    st.success("AI 문제 준비 완료!")

    st.divider()

    # --- 라이브 제어판 ---
    st.subheader("🚀 라이브 진행 제어")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.write(f"**현재 상태:** `{game['status'].upper()}`")
        if game["questions"]:
            st.write(f"**현재 진행:** {game['current_question'] + 1} / {len(game['questions'])} 번 문제")
    
    with col_s2:
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
                        # 퀴즈 종료 ➔ 점수 자동 채점
                        game["status"] = "ended"
                        scores = {}
                        for q_idx, q_data in enumerate(game["questions"]):
                            user_ans_dict = game["answers"].get(q_idx, {})
                            correct_ans_num = q_data["ans"] # 예: "2"
                            for nick, selected_option in user_ans_dict.items():
                                if selected_option.startswith(correct_ans_num):
                                    scores[nick] = scores.get(nick, 0) + 1
                                else:
                                    scores[nick] = scores.get(nick, 0)
                        game["scores"] = scores
                st.rerun()

    # --- 진행 화면 ---
    if game["status"] == "playing" and game["questions"]:
        st.divider()
        q_data = game["questions"][game["current_question"]]
        st.header(f"📢 Q{game['current_question']+1}. {q_data['q']}")
        for opt in q_data["options"]:
            st.subheader(f"  {opt}")
        
        curr_q = game["current_question"]
        submits = game["answers"].get(curr_q, {})
        st.info(f"👥 현재 정답 제출 참가자 수: **{len(submits)}명**")

    # --- 최종 리더보드 (Top 5) ---
    elif game["status"] == "ended":
        st.divider()
        st.header("🏆 최종 결과 TOP 5 리더보드")
        if game["scores"]:
            sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
            for rank, (nick, score) in enumerate(sorted_scores, 1):
                icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                st.subheader(f"{icon} **{rank}위**: {nick} — {score}점 / {len(game['questions'])}점 만점")
        else:
            st.write("제출된 답안이 없습니다.")

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
                
                st.subheader(f"문제 {curr_q + 1}. {q_data['q']}")
                user_ans = st.radio("정답을 선택하세요:", q_data["options"], key=f"ans_{curr_q}")
                
                if st.button("정답 제출하기", key=f"btn_{curr_q}"):
                    if curr_q not in game["answers"]:
                        game["answers"][curr_q] = {}
                    game["answers"][curr_q][nickname] = user_ans
                    st.success("답안이 제출되었습니다! 다음 문제를 기다려주세요.")
            
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
                    st.info(f"🙋‍♂️ **{nickname}**님의 최종 점수: 총 **{my_score}개** 맞추셨습니다!")

        show_quiz_for_user()
