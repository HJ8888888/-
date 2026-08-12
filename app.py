import streamlit as st
import pandas as pd
import time
import os
from google import genai

# 페이지 설정
st.set_page_config(page_title="라이브 퀴즈 챌린지 🌸", layout="wide")

# ---------------------------------------------------------
# 🎨 화사한 파스텔 핑크 테마 Custom CSS 적용
# ---------------------------------------------------------
st.markdown("""
    <style>
    /* 1. 전체 앱 메인 배경색 (소프트 파스텔 핑크) */
    .stApp {
        background-color: #FFF5F7;
        color: #4A2E35;
    }
    
    /* 2. 사이드바 디자인 (블러쉬 핑크) */
    [data-testid="stSidebar"] {
        background-color: #FCE4EC !important;
        border-right: 1px solid #F8BBD0;
    }
    
    /* 3. 메인 제목 및 섹션 헤더 글자색 (딥 로즈) */
    h1, h2, h3, h4, h5, h6, .stText {
        color: #880E4F !important;
        font-family: 'Pretendard', sans-serif;
    }
    
    /* 4. 기본 버튼 스타일 (파스텔 로즈 핑크) */
    .stButton > button {
        background-color: #FFC1CC !important;
        color: #5A1827 !important;
        border-radius: 15px !important;
        border: 2px solid #FF9EAA !important;
        font-weight: bold !important;
        font-size: 16px !important;
        padding: 10px 20px !important;
        box-shadow: 0px 4px 10px rgba(255, 182, 193, 0.4);
        transition: all 0.3s ease !important;
    }
    
    /* 버튼에 마우스 올렸을 때 */
    .stButton > button:hover {
        background-color: #FF80BF !important;
        color: #FFFFFF !important;
        border-color: #FF4D94 !important;
        transform: translateY(-2px);
    }
    
    /* 5. 입력창, 텍스트 에어리어 스타일 */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea, .stNumberInput > div > div > input {
        background-color: #FFFFFF !important;
        border: 2px solid #F8BBD0 !important;
        border-radius: 12px !important;
        color: #4A2E35 !important;
    }
    
    .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {
        border-color: #FF69B4 !important;
        box-shadow: 0 0 8px rgba(255, 105, 180, 0.3) !important;
    }

    /* 6. 알림/안내 상자 (Success, Info, Warning, Error) 핑크 톤 커스텀 */
    .stAlert {
        border-radius: 15px !important;
        border: none !important;
        box-shadow: 0px 3px 8px rgba(0,0,0,0.05);
    }
    
    /* 7. 프로그레스 바 (타이머) 칼라 */
    .stProgress > div > div > div > div {
        background-color: #FF69B4 !important;
    }

    /* 8. 탭 디자인 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0px 0px;
        padding: 8px 16px;
        background-color: #FFE4E1;
        color: #880E4F;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFB6C1 !important;
        color: #5A1827 !important;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 🔑 진행자 전용 비밀번호 설정
# ---------------------------------------------------------
HOST_PASSWORD = "sunghejinH8!"

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

# 엑셀 데이터 파싱 함수
def parse_df_to_questions(df):
    parsed_questions = []
    for _, row in df.iterrows():
        q_text = str(row["문제"]).strip()
        ans_text = str(row["정답"]).strip()
        
        is_obj = "보기1" in df.columns and pd.notna(row.get("보기1")) and str(row.get("보기1")).strip() != ""
        
        if is_obj:
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
    return parsed_questions

# GitHub에 저장된 quiz.xlsx/csv 자동 로딩
if not game["questions"]:
    default_file = None
    if os.path.exists("quiz.xlsx"):
        default_file = "quiz.xlsx"
    elif os.path.exists("quiz.csv"):
        default_file = "quiz.csv"
        
    if default_file:
        try:
            df = pd.read_csv(default_file) if default_file.endswith(".csv") else pd.read_excel(default_file)
            game["questions"] = parse_df_to_questions(df)
        except Exception:
            pass

st.sidebar.title("🎮 접속 모드")
role = st.sidebar.radio("역할을 선택하세요", ["📱 참가자 (User)", "🎙️ 진행자 (Host)"])

# ---------------------------------------------------------
# 🎙️ 진행자 (Host) 화면
# ---------------------------------------------------------
if role == "🎙️ 진행자 (Host)":
    st.sidebar.divider()
    input_pw = st.sidebar.text_input("🔑 진행자 비밀번호 입력:", type="password")
    
    # 비밀번호 검증
    if input_pw != HOST_PASSWORD:
        st.title("🔒 진행자 전용 구역")
        st.warning("진행자 비밀번호가 올바르지 않습니다. 왼쪽 사이드바에서 비밀번호를 입력해주세요!")
        st.info("💡 일반 참가자분들은 사이드바에서 **'📱 참가자 (User)'** 모드를 선택해 주시기 바랍니다.")
    else:
        st.title("🎙️ 진행자 라이브 제어판 🌸")
        
        # 제한 시간 설정
        game["timer_sec"] = st.number_input("⏱️ 문제당 제한 시간(초)을 설정하세요:", min_value=5, max_value=120, value=15, step=5)
        
        tab1, tab2, tab3 = st.tabs(["📊 엑셀/CSV 업로드", "✍️ 직접 입력", "✨ AI 자동 생성"])
        
        # --- 탭 1: 엑셀 파일 업로드 ---
        with tab1:
            st.subheader("📁 엑셀(.xlsx) 파일로 문제 등록")
            if os.path.exists("quiz.xlsx") or os.path.exists("quiz.csv"):
                st.success("💾 **GitHub에 저장된 기본 엑셀(quiz.xlsx)이 로딩되어 있습니다.**")
                if st.button("🔄 저장된 quiz.xlsx 문제로 다시 초기화하기"):
                    file_path = "quiz.xlsx" if os.path.exists("quiz.xlsx") else "quiz.csv"
                    df = pd.read_csv(file_path) if file_path.endswith(".csv") else pd.read_excel(file_path)
                    game["questions"] = parse_df_to_questions(df)
                    game["current_question"] = 0
                    game["status"] = "waiting"
                    game["answers"] = {}
                    game["scores"] = {}
                    st.rerun()

            uploaded_file = st.file_uploader("새로운 엑셀 또는 CSV 파일 선택", type=["xlsx", "csv"])
            if uploaded_file is not None:
                try:
                    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                    st.write("📋 미리보기:", df.head())
                    
                    if st.button("📊 이 새로 올린 엑셀로 문제 바꾸기"):
                        game["questions"] = parse_df_to_questions(df)
                        game["current_question"] = 0
                        game["status"] = "waiting"
                        game["answers"] = {}
                        game["scores"] = {}
                        st.success(f"🎉 총 {len(game['questions'])}개의 새 문제가 준비되었습니다!")
                except Exception as e:
                    st.error(f"오류가 발생했습니다. 열 이름을 확인해주세요! ({e})")

        # --- 탭 2: 직접 입력 ---
        with tab2:
            st.subheader("내가 원하는 문제 직접 입력")
            default_sample = "파이썬은 초보자가 배우기 쉬운 프로그래밍 언어이다. | O, X | 1"
            q_text = st.text_area("문제 입력:", value=default_sample, height=100)
            
            if st.button("📝 텍스트 문제 등록하기"):
                parsed_questions = []
                for line in q_text.strip().split("\n"):
                    parts = line.split("|")
                    if len(parts) == 2:
                        parsed_questions.append({"q": parts[0].strip(), "type": "subjective", "options": [], "ans": parts[1].strip()})
                    elif len(parts) == 3:
                        raw_opts = [opt.strip() for opt in parts[1].split(",") if opt.strip()]
                        opts = [f"{i+1}. {opt}" for i, opt in enumerate(raw_opts)]
                        parsed_questions.append({"q": parts[0].strip(), "type": "objective", "options": opts, "ans": parts[2].strip()})
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
                    {"q": "Q2. 물의 화학식은 H2O이다.", "type": "objective", "options": ["1. O", "2. X"], "ans": "1"}
                ]
                game["current_question"] = 0
                game["status"] = "waiting"
                game["answers"] = {}
                game["scores"] = {}
                st.success("AI OX 문제 준비 완료!")

        st.divider()

        # --- 실시간 진행 제어 (1초 단위 자동 갱신) ---
        @st.fragment(run_every="1s")
        def show_host_dashboard():
            st.subheader("🚀 라이브 진행 제어")
            p_count = len(game["participants"])
            st.info(f"👥 **현재 입장한 참가자 ({p_count}명):** " + (", ".join([f"`{p}`" for p in game["participants"]]) if game["participants"] else "아직 입장한 참가자가 없습니다."))
            
            # 제어 버튼 배치 (시작/다음 + 초기화 버튼)
            col1, col2 = st.columns([2, 1])
            
            with col1:
                if st.button("▶️ 게임 시작 / 다음 문제 넘어가기", use_container_width=True):
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
                                game["status"] = "ended"
                                # 들어온 모든 참가자 점수 0점으로 초기화 후 채점
                                scores = {p: 0 for p in game["participants"]}
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
                                            norm_user = user_ans_clean.replace(" ", "").lower()
                                            norm_corr = correct_ans.replace(" ", "").lower()
                                            if norm_user == norm_corr:
                                                scores[nick] = scores.get(nick, 0) + 1
                                game["scores"] = scores
                        
                        game["q_start_time"] = time.time()
                        st.rerun()

            with col2:
                if st.button("🔄 접속자 & 게임 전체 초기화", use_container_width=True):
                    game["status"] = "waiting"
                    game["current_question"] = 0
                    game["answers"] = {}
                    game["scores"] = {}
                    game["participants"] = []
                    st.success("🎉 참가자 명단 및 진행 상태가 깨끗하게 초기화되었습니다!")
                    st.rerun()

            # --- 현재 진행 문제 및 실시간 타이머 표시 ---
            if game["status"] == "playing" and game["questions"]:
                st.divider()
                q_data = game["questions"][game["current_question"]]
                q_type_str = "주관식" if q_data.get("type") == "subjective" else "객관식/OX"
                
                elapsed = time.time() - game.get("q_start_time", time.time())
                limit = game.get("timer_sec", 15)
                time_left = max(0, int(limit - elapsed))
                
                st.header(f"📢 Q{game['current_question']+1} [{q_type_str}]. {q_data['q']}")
                
                if time_left > 0:
                    st.progress(time_left / limit, text=f"⏱️ 남은 시간: **{time_left}초**")
                else:
                    st.error("⏰ 제한 시간이 종료되었습니다! 더 이상 답안 제출이 불가능합니다.")
                
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
                st.header("🏆 전체 참가자 최종 순위 리더보드 👑")
                if game["scores"]:
                    # 참가자 전체 순위 출력 (전체 정렬)
                    sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)
                    for rank, (nick, score) in enumerate(sorted_scores, 1):
                        icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                        st.subheader(f"{icon} **{rank}위**: {nick} — {score}점 / {len(game['questions'])}점 만점")

        show_host_dashboard()

# ---------------------------------------------------------
# 📱 참가자 (Participant) 화면
# ---------------------------------------------------------
else:
    st.title("📱 라이브 퀴즈 참가하기 💖")
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
                st.subheader("🏆 전체 참가자 최종 순위 👑")
                if game["scores"]:
                    # 참가자 전체 순위 출력 (전체 정렬)
                    sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)
                    for rank, (nick, score) in enumerate(sorted_scores, 1):
                        icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else "🏅"
                        st.write(f"{icon} **{rank}위**: {nick} ({score}점)")
                    st.divider()
                    my_score = game["scores"].get(nickname, 0)
                    st.info(f"🙋‍♂️ **{nickname}**님의 최종 점수: **{my_score}개** 맞추셨습니다!")

        show_quiz_for_user()
