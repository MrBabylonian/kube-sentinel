# ChatService Unit Tests - Test Cases

## Existing Tests
- ✅ `test_history_initialization` – Verifies history starts with one system message

## Proposed Test Cases

### Core Functionality
1. **`test_stream_success`** – Verify successful message streaming with multiple token chunks
2. **`test_stream_appends_to_history`** – Verify human messages and AI responses are added to history correctly
3. **`test_clear_chat_history`** – Verify history is reset to just the system message

### Error Handling
4. **`test_stream_empty_input`** – Verify `ChatStreamError` is raised for empty/whitespace user input
5. **`test_stream_with_llm_error`** – Verify `ChatProviderError` is raised when LLM provider encounters an error
6. **`test_stream_with_cancelled_error`** – Verify rollback occurs when stream is cancelled via `asyncio.CancelledError`
7. **`test_stream_with_validation_error`** – Verify `ChatStreamError` is raised on response validation failure

### Token Extraction
8. **`test_extract_token_text_string`** – Test text extraction from plain string chunks
9. **`test_extract_token_text_list`** – Test text extraction from list chunks containing strings
10. **`test_extract_token_text_list_with_dict`** – Test text extraction from list chunks with dict items containing 'text' field
11. **`test_extract_token_text_mixed`** – Test text extraction from mixed list (strings + dicts)
12. **`test_extract_token_text_empty_input`** – Verify empty string returned for unsupported chunk types

### Message Rollback
13. **`test_rollback_user_turn_removes_message`** – Verify message is removed on rollback
14. **`test_rollback_user_turn_no_message_available`** – Verify no error when rolling back with empty history (except system message)

### State Management
15. **`test_history_independence`** – Verify returned history is a deep copy and changes don't affect internal state
16. **`test_multiple_sequential_streams`** – Verify correct message accumulation across multiple stream calls
