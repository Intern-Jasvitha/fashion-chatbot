import { Routes, Route, Navigate } from 'react-router-dom'
import { MainChatPage } from './components/main-chat-page'
import { ChatbotWidget } from './components/chatbot'
import { ChatSessionProvider } from './contexts/chat-session-context'
import { ProtectedRoute } from './components/protected-route'
import { LoginPage } from './pages/login'
import { SignupPage } from './pages/signup'

function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route
            path="/"
            element={
              <ChatSessionProvider>
                <MainChatPage />
                <ChatbotWidget />
              </ChatSessionProvider>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App