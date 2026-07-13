import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Supabase 서버 전용 클라이언트를 생성한다.
 *
 * - Server Component / 서버 사이드 읽기 전용 조회에서만 사용한다.
 * - 세션 저장을 비활성화한다(persistSession: false). anon 키 + RLS(SELECT-only) 환경이므로
 *   브라우저 세션 상태를 유지할 필요가 없다.
 * - 환경변수는 클라이언트 생성 시점(호출 시점)에만 검증한다. 이렇게 하면 환경변수가 없는
 *   빌드 환경에서도 모듈 import 만으로는 실패하지 않는다.
 */
export function createSupabaseServerClient(): SupabaseClient {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl) {
    throw new Error(
      "환경변수 NEXT_PUBLIC_SUPABASE_URL 이 설정되지 않았습니다. Supabase 클라이언트를 생성할 수 없습니다.",
    );
  }

  if (!supabaseAnonKey) {
    throw new Error(
      "환경변수 NEXT_PUBLIC_SUPABASE_ANON_KEY 이 설정되지 않았습니다. Supabase 클라이언트를 생성할 수 없습니다.",
    );
  }

  return createClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
}
