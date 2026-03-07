# ChatService Unit Tests - Test Cases

## Implementation Status: 8/16 (50%)

## Implemented Tests ✅
- ✅ `test_history_initialization` – Verifies history starts with one system message
- ✅ `test_stream_success` – Verify successful message streaming with multiple token chunks
- ✅ `test_stream_appends_to_history` – Verify human messages and AI responses are added to history correctly
- ✅ `test_clear_chat_history` – Verify history is reset to just the system message
- ✅ `test_stream_empty_input` – Verify `ChatStreamError` is raised for empty/whitespace user input
- ✅ `test_stream_with_llm_error` – Verify `ChatProviderError` is raised when LLM provider encounters an error
- ✅ `test_stream_with_cancelled_error` – Verify rollback occurs when stream is cancelled via `asyncio.CancelledError`

## Pending Test Cases ⏳

### Core Functionality

### Error Handling
- 🚫 `test_stream_with_validation_error` – SKIPPED: No response schema validation mechanism in place. Revisit when structured output is implemented in `ChatService`.

### Token Extraction
- 🚫 `test_extract_token_text_string` – DEFERRED: Move to integration test suite. Testing via `stream()` crosses unit boundary.
- 🚫 `test_extract_token_text_list` – DEFERRED: Move to integration test suite. Testing via `stream()` crosses unit boundary.
- 🚫 `test_extract_token_text_list_with_dict` – DEFERRED: Move to integration test suite. Testing via `stream()` crosses unit boundary.
- 🚫 `test_extract_token_text_mixed` – DEFERRED: Move to integration test suite. Testing via `stream()` crosses unit boundary.
- 🚫 `test_extract_token_text_empty_input` – DEFERRED: Move to integration test suite. Testing via `stream()` crosses unit boundary.

### Message Rollback
- 🚫 `test_rollback_user_turn_removes_message` – DEFERRED: Already covered indirectly by `test_stream_with_llm_error` and `test_stream_with_cancelled_error`.
- 🚫 `test_rollback_user_turn_no_message_available` – DEFERRED: `_rollback_user_turn` is a silent no-op when message is not at tail. Already covered by existing error tests.

### State Management
- ✅ `test_history_independence` – Verify returned history is a deep copy and changes don't affect internal state
- 🚫 `test_multiple_sequential_streams` – DEFERRED: Already fully covered by `test_stream_appends_to_history`.
