import streamlit as st
from helper import streaming_response_generator

st.title("Hỏi đáp y khoa với Meddy 🤓")
st.markdown(
    """
**Xin chào, tôi là Meddy!** 🤗\n
Tôi ở đây để giúp bạn giải quyết, tra cứu các thông tin trong lĩnh vực y tế. Hãy cứ thoải mái hỏi tôi bất cứ điều gì trong phạm trù kiến thức y khoa, tôi sẽ làm hết sức mình để hỗ trợ bạn!
"""
)


if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Tôi có thể giúp gì cho bạn?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            for chunk in streaming_response_generator(prompt):
                if chunk == ".":
                    message_placeholder.markdown("🤔 Đang suy nghĩ...")
                    continue

                full_response += chunk
                # Display with cursor during streaming
                message_placeholder.markdown(full_response + "▌")

            # Final display without cursor
            message_placeholder.markdown(full_response)

            if full_response.strip():
                st.session_state.messages.append(
                    {"role": "assistant", "content": full_response}
                )
        except Exception:
            error_message = "❌ Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại."
            message_placeholder.markdown(error_message)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_message}
            )

with st.sidebar:
    st.sidebar.button(
        "🗑️ Xóa lịch sử trò chuyện",
        on_click=lambda: st.session_state.update(messages=[]),
        type="primary",
        help="Xóa toàn bộ cuộc trò chuyện hiện tại",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
    ### 💡 Hướng dẫn sử dụng
    - Bạn hãy đặt các câu hỏi liên quan đến y khoa, ví dụ:
        - "Triệu chứng của bệnh tiểu đường là gì?"
        - "Làm thế nào để phòng ngừa cảm cúm?"
    - Meddy sẽ trả lời dựa trên kiến thức y khoa và các tài liệu đã được cung cấp
    - Sử dụng nút "Xóa lịch sử trò chuyện" để bắt đầu cuộc trò chuyện mới
    """
    )
