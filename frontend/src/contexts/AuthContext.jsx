import { createContext, useContext, useState, useEffect } from "react";
import { supabase } from "../supabaseClient.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mfaChallenge, setMfaChallenge] = useState(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setUser(s?.user ?? null);
      if (s?.user) fetchProfile(s.user.id);
      else setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setUser(s?.user ?? null);
      if (s?.user) {
        setMfaChallenge(null);
        fetchProfile(s.user.id);
      } else {
        setProfile(null);
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  async function fetchProfile(userId) {
    try {
      const { data } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", userId)
        .single();
      setProfile(data);
    } catch {
      // Profile may not exist yet on first signup
    } finally {
      setLoading(false);
    }
  }

  async function signUp(email, password) {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    return data;
  }

  async function signIn(email, password) {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;

    // Supabase returns a session if no MFA, or an empty session with mfa metadata if MFA is required
    if (data?.session) {
      return data;
    }

    // MFA required — get the TOTP factor and create a challenge
    const factors = data?.user?.factors ?? [];
    const totpFactor = factors.find((f) => f.factor_type === "totp" && f.status === "verified");

    if (!totpFactor) {
      // Fallback: check via the MFA API
      const { data: assuranceData } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
      if (assuranceData?.nextLevel === "aal2" && assuranceData?.currentLevel === "aal1") {
        const { data: factorsList } = await supabase.auth.mfa.listFactors();
        const totp = factorsList?.totp?.find((f) => f.status === "verified");
        if (totp) {
          const { data: challenge, error: challengeErr } = await supabase.auth.mfa.challenge({ factorId: totp.id });
          if (challengeErr) throw challengeErr;
          setMfaChallenge({ factorId: totp.id, challengeId: challenge.id });
          return { mfaRequired: true };
        }
      }
      throw new Error("MFA factor not found. Please contact support.");
    }

    const { data: challenge, error: challengeErr } = await supabase.auth.mfa.challenge({ factorId: totpFactor.id });
    if (challengeErr) throw challengeErr;

    setMfaChallenge({ factorId: totpFactor.id, challengeId: challenge.id });
    return { mfaRequired: true };
  }

  async function verifyMfa(code) {
    if (!mfaChallenge) throw new Error("No MFA challenge in progress");

    const { data, error } = await supabase.auth.mfa.verify({
      factorId: mfaChallenge.factorId,
      challengeId: mfaChallenge.challengeId,
      code,
    });
    if (error) throw error;

    setMfaChallenge(null);
    return data;
  }

  function cancelMfa() {
    setMfaChallenge(null);
  }

  async function signInWithGoogle() {
    console.log("Initiating Google Sign-In with redirect:", window.location.origin + "/oauth/callback");
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin + "/oauth/callback" },
    });
    if (error) {
      console.error("Google Sign-In Error:", error);
      throw error;
    }
    return data;
  }

  async function signInWithApple() {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "apple",
      options: { redirectTo: window.location.origin + "/oauth/callback" },
    });
    if (error) throw error;
    return data;
  }

  async function signOut() {
    await supabase.auth.signOut();
    setUser(null);
    setSession(null);
    setProfile(null);
    setMfaChallenge(null);
  }

  async function refreshProfile() {
    if (user) await fetchProfile(user.id);
  }

  const value = {
    user,
    session,
    profile,
    loading,
    mfaChallenge,
    signUp,
    signIn,
    verifyMfa,
    cancelMfa,
    signInWithGoogle,
    signInWithApple,
    signOut,
    refreshProfile,
    accessToken: session?.access_token,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
