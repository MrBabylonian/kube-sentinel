class ChatServiceError(Exception):
    pass

class ChatConfigurationError(ChatServiceError):
    pass

class ChatProviderError(ChatServiceError):
    pass

class ChatStreamError(ChatServiceError):
    pass

