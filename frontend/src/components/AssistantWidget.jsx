import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

// ==========================================
// MARITIME AI ASSISTANT - CHAT UI
// ==========================================
// A presentation-only chat window for the EXISTING
// chatbot backend. It adds no AI logic of its own:
//
//   Chat UI
//     -> POST /api/assistant/chat          (scope "user")
//     -> POST /api/admin/assistant/chat   (scope "admin")
//        -> existing intent detection
//        -> existing Gemini explanation layer
//     -> response rendered here
//
// The same component serves both dashboards. Only the
// requested URLs, the title and the subtitle change, so
// the two assistants can never drift apart.
//
// DESIGN RULES ENFORCED HERE
// * The backend identifies the caller from the bearer
//   token, so this file NEVER sends a user_id. The
//   authenticated token is the only identity source.
// * Suggestions are rendered exactly as the existing
//   suggestions endpoint returns them. There is no local
//   fallback list, so the UI cannot advertise a question
//   the assistant cannot answer.
// * No number, route score, weather risk or customs
//   status is computed here. Every value in an answer
//   came from the backend.
// * Conversation history lives in this component's
//   session state only. The backend is stateless per
//   request, so nothing is persisted and no second
//   memory system is introduced.
// * A failed request degrades to a friendly in-window
//   message and never throws out of the component, so
//   the surrounding dashboard keeps working.
// ==========================================

// Keeps parity with AssistantRequest on the backend.
const MAX_MESSAGE_CHARS = 1000;

// One friendly message for every failure mode, so the
// dashboard never shows a raw stack trace or a cryptic
// network string to the user.
const UNAVAILABLE_MESSAGE =
  "AI Assistant is temporarily unavailable. Please try again.";

const SESSION_EXPIRED_MESSAGE =
  "Your session has expired. Please sign in again.";

const EMPTY_MESSAGE_ERROR =
  "Please enter a question for the Maritime AI Assistant.";

// A chat request is never allowed to hang. The backend has its
// own timeout on the explanation service, so this is a safety
// net for the whole round trip rather than a tuning knob.
const REQUEST_TIMEOUT_MS = 20000;

// fetch() with a hard deadline, so a stalled request always
// resolves into the friendly unavailable message instead of
// leaving the widget spinning forever.
const fetchWithTimeout = async (
  url,
  options,
  timeoutMs = REQUEST_TIMEOUT_MS
) => {
  const controller = new AbortController();

  const timer = setTimeout(
    () => controller.abort(),
    timeoutMs
  );

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
};

const SCOPE_CONFIG = {
  user: {
    title: "Maritime AI Assistant",
    subtitle: "Your route, weather & shipment data",
    chatUrl: "/api/assistant/chat",
    suggestionsUrl: "/api/assistant/suggestions",
    emptyLabel: "How can I help? Ask about your route, quotation, customs, weather or shipment.",
  },
  admin: {
    title: "Admin Maritime AI Assistant",
    subtitle: "Platform-wide operations data",
    chatUrl: "/api/admin/assistant/chat",
    suggestionsUrl: "/api/admin/assistant/suggestions",
    emptyLabel: "How can I help? Ask about shipments, users, quotations or system health.",
  },
};

const messageId = () =>
  `assistant-message-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;

// Renders the backend answer as plain text. The response
// is assistant prose, not markup, so it is deliberately
// never injected as HTML.
const AssistantMessageText = ({ content }) => (
  <p className="assistant-bubble-text">{content}</p>
);

function AssistantWidget({
  scope = "user",
  getAuthHeaders,
}) {
  const config = SCOPE_CONFIG[scope] || SCOPE_CONFIG.user;

  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] =
    useState(false);
  const [suggestionsError, setSuggestionsError] =
    useState("");
  const [aiStatus, setAiStatus] = useState("ready");

  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const didLoadSuggestions = useRef(false);

  // -------------------------------------------------
  // ALWAYS SCROLL TO THE NEWEST MESSAGE
  // -------------------------------------------------

  useEffect(() => {
    if (!scrollRef.current) return;

    scrollRef.current.scrollTop =
      scrollRef.current.scrollHeight;
  }, [messages, isSending]);

  // -------------------------------------------------
  // LOAD SUGGESTIONS FROM THE EXISTING API
  // -------------------------------------------------
  // Fetched once, the first time the window is opened,
  // and re-fetched when the scope changes so an admin
  // never sees the user starter questions.

  const loadSuggestions = useCallback(async () => {
    setIsLoadingSuggestions(true);
    setSuggestionsError("");

    try {
      const response = await fetchWithTimeout(
        config.suggestionsUrl,
        {
          headers: {
            ...(getAuthHeaders ? getAuthHeaders() : {}),
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          `Suggestions request failed with ${response.status}`
        );
      }

      const data = await response
        .json()
        .catch(() => ({}));

      const list = Array.isArray(data?.suggestions)
        ? data.suggestions.filter(
            (item) => typeof item === "string" && item.trim()
          )
        : [];

      setSuggestions(list);

      if (!list.length) {
        setSuggestionsError(
          "No suggestions are available right now."
        );
      }
    } catch {
      // A missing suggestion list must not break the
      // chat window; the user can still type a question.
      setSuggestions([]);
      setSuggestionsError(
        "Suggested questions could not be loaded."
      );
    } finally {
      setIsLoadingSuggestions(false);
    }
  }, [config.suggestionsUrl, getAuthHeaders]);

  useEffect(() => {
    if (!isOpen) return;
    if (didLoadSuggestions.current) return;

    didLoadSuggestions.current = true;

    loadSuggestions();
  }, [isOpen, loadSuggestions]);

  // A different scope is a different assistant with its own
  // starter questions. The panel is mounted with `key={scope}`
  // by the dashboard, so switching scope remounts it with clean
  // state rather than clearing state from inside an effect.

  // -------------------------------------------------
  // OPEN / CLOSE
  // -------------------------------------------------

  const openAssistant = () => {
    setIsOpen(true);
    setAiStatus("ready");
  };

  const closeAssistant = () => {
    setIsOpen(false);
    setNotice("");
  };

  // Escape closes the window, matching the dialog
  // behaviour users expect from a floating panel.
  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        closeAssistant();
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () =>
      window.removeEventListener("keydown", onKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // -------------------------------------------------
  // SEND A QUESTION TO THE EXISTING CHAT API
  // -------------------------------------------------
  // `message` is the only field sent. No user_id, no
  // role and no shipment reference is included: the
  // backend derives the caller from the token and
  // reads only that caller's own records.

  const sendMessage = async (rawText) => {
    const question = String(rawText || "").trim();

    if (!question) {
      setNotice(EMPTY_MESSAGE_ERROR);
      return;
    }

    if (question.length > MAX_MESSAGE_CHARS) {
      setNotice(
        `Please keep your question under ${MAX_MESSAGE_CHARS} characters.`
      );
      return;
    }

    setNotice("");
    setDraft("");
    setIsSending(true);
    setAiStatus("thinking");

    setMessages((previous) => [
      ...previous,
      {
        id: messageId(),
        role: "user",
        content: question,
      },
    ]);

    try {
      const response = await fetchWithTimeout(
        config.chatUrl,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(getAuthHeaders ? getAuthHeaders() : {}),
          },
          body: JSON.stringify({ message: question }),
        }
      );

      // An expired or unauthorised token is reported as
      // a sign-in problem rather than a generic outage.
      if (response.status === 401 || response.status === 403) {
        throw new Error(
          `Authentication failed with ${response.status}`
        );
      }

      if (!response.ok) {
        throw new Error(
          `Chat request failed with ${response.status}`
        );
      }

      const data = await response
        .json()
        .catch(() => ({}));

      const answer =
        typeof data?.answer === "string" && data.answer.trim()
          ? data.answer.trim()
          : typeof data?.deterministic_answer === "string" &&
              data.deterministic_answer.trim()
            ? data.deterministic_answer.trim()
            : UNAVAILABLE_MESSAGE;

      setMessages((previous) => [
        ...previous,
        {
          id: messageId(),
          role: "assistant",
          content: answer,
          // The backend already falls back to a
          // deterministic answer when the explanation
          // service is not reachable, so the answer is still
          // shown.
          source: data?.answer_source || "deterministic",
        },
      ]);

      setAiStatus(
        data?.explanation_available === false
          ? "deterministic"
          : "ready"
      );

      // The backend never sends an internal reason or a model
      // name, so there is nothing technical to surface here.
      setNotice("");
    } catch (error) {
      const message =
        String(error?.message || "").includes(
          "Authentication failed"
        )
          ? SESSION_EXPIRED_MESSAGE
          : UNAVAILABLE_MESSAGE;

      setMessages((previous) => [
        ...previous,
        {
          id: messageId(),
          role: "assistant",
          content: message,
          isError: true,
        },
      ]);

      setNotice("");
      setAiStatus("error");
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    sendMessage(draft);
  };

  const handleInputKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();

      sendMessage(draft);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    sendMessage(suggestion);
  };

  // Session-only reset. The backend holds no chat memory,
  // so clearing the local transcript is a complete and
  // honest "new conversation".
  const clearConversation = () => {
    setMessages([]);
    setNotice("");
    setAiStatus("ready");

    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const aiStatusLabel = {
    ready: "Online",
    thinking: "Thinking",
    deterministic: "Limited mode",
    error: "Unavailable",
  }[aiStatus];

  return (
    <div
      className={`assistant-widget assistant-widget-${scope}`}
    >
      {/* CHAT WINDOW */}

      {isOpen && (
        <section
          className="assistant-panel"
          role="dialog"
          aria-label={config.title}
        >
          <header className="assistant-header">
            <div className="assistant-header-identity">
              <span
                className="assistant-avatar"
                aria-hidden="true"
              >
                AI
              </span>

              <div className="assistant-header-text">
                <strong className="assistant-title">
                  {config.title}
                </strong>

                <span className="assistant-subtitle">
                  {config.subtitle}
                </span>

                <span
                  className={`assistant-status assistant-status-${aiStatus}`}
                >
                  <span
                    className="assistant-status-dot"
                    aria-hidden="true"
                  />
                  {aiStatusLabel}
                </span>
              </div>
            </div>

            <div className="assistant-header-actions">
              <button
                type="button"
                className="assistant-icon-button"
                onClick={clearConversation}
                disabled={isSending || !messages.length}
                title="Clear conversation"
                aria-label="Clear conversation"
              >
                ↻
              </button>

              <button
                type="button"
                className="assistant-icon-button assistant-close-button"
                onClick={closeAssistant}
                title="Close assistant"
                aria-label="Close assistant"
              >
                ✕
              </button>
            </div>
          </header>

          <div
            className="assistant-scroll"
            ref={scrollRef}
          >
            {/* FIRST OPENING: SUGGESTIONS FROM THE API */}

            {!messages.length && (
              <div className="assistant-intro">
                <p className="assistant-intro-text">
                  {config.emptyLabel}
                </p>

                {isLoadingSuggestions && (
                  <p className="assistant-hint">
                    Loading suggested questions…
                  </p>
                )}

                {!isLoadingSuggestions &&
                  suggestionsError && (
                    <p className="assistant-hint">
                      {suggestionsError}
                    </p>
                  )}

                {!isLoadingSuggestions &&
                  !suggestionsError &&
                  suggestions.length > 0 && (
                    <div className="assistant-suggestions">
                      <span className="assistant-suggestions-label">
                        Try asking
                      </span>

                      {suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          className="assistant-suggestion"
                          onClick={() =>
                            handleSuggestionClick(
                              suggestion
                            )
                          }
                          disabled={isSending}
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
              </div>
            )}

            {/* MESSAGES */}

            {messages.map((message) => (
              <div
                key={message.id}
                className={`assistant-message assistant-message-${message.role}${
                  message.isError
                    ? " assistant-message-error"
                    : ""
                }`}
              >
                {message.role === "assistant" && (
                  <span
                    className="assistant-message-avatar"
                    aria-hidden="true"
                  >
                    AI
                  </span>
                )}

                <div className="assistant-bubble">
                  <AssistantMessageText
                    content={message.content}
                  />

                  {message.role === "assistant" &&
                    message.source ===
                      "deterministic" &&
                    !message.isError && (
                      <span className="assistant-bubble-note">
                        Answered from your stored results
                      </span>
                    )}
                </div>
              </div>
            ))}

            {/* TYPING INDICATOR */}

            {isSending && (
              <div className="assistant-message assistant-message-assistant">
                <span
                  className="assistant-message-avatar"
                  aria-hidden="true"
                >
                  AI
                </span>

                <div className="assistant-bubble assistant-typing">
                  <span className="assistant-typing-dot" />
                  <span className="assistant-typing-dot" />
                  <span className="assistant-typing-dot" />
                  <span className="sr-only">
                    The assistant is preparing an answer.
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* PLAIN-LANGUAGE NOTICE */}
          {/* Only ever a customer-facing sentence. Technical
              reasons are never sent by the backend. */}

          {notice && (
            <p
              className="assistant-notice"
              role="status"
            >
              {notice}
            </p>
          )}

          <form
            className="assistant-composer"
            onSubmit={handleSubmit}
          >
            <label
              className="assistant-composer-label"
              htmlFor={`assistant-input-${scope}`}
            >
              Ask about your shipment
            </label>

            <div className="assistant-composer-row">
              <textarea
                id={`assistant-input-${scope}`}
                ref={inputRef}
                className="assistant-input"
                value={draft}
                rows={1}
                maxLength={MAX_MESSAGE_CHARS}
                placeholder="Ask about your shipment"
                onChange={(event) =>
                  setDraft(event.target.value)
                }
                onKeyDown={handleInputKeyDown}
                disabled={isSending}
              />

              <button
                type="submit"
                className="assistant-send-button"
                disabled={
                  isSending || !String(draft).trim()
                }
                title="Send question"
                aria-label="Send question"
              >
                ➤
              </button>
            </div>
          </form>
        </section>
      )}

      {/* FLOATING LAUNCH BUTTON */}

      <button
        type="button"
        className="assistant-launcher"
        onClick={() =>
          isOpen ? closeAssistant() : openAssistant()
        }
        aria-expanded={isOpen}
        aria-label={
          isOpen
            ? `Close ${config.title}`
            : `Open ${config.title}`
        }
        title={config.title}
      >
        {isOpen ? "✕" : "AI"}
      </button>
    </div>
  );
}

export default AssistantWidget;