import { createContext, useContext } from 'react'

/** 로그인한 사용자와 권한 확인 함수를 화면 전체에 전달한다. */
export const AuthContext = createContext({ user: null, can: () => false })

export const useAuth = () => useContext(AuthContext)
