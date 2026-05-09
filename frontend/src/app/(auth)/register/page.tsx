"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuthStore } from "@/lib/auth/session";
import { api } from "@/lib/api/client";

const registerSchema = z.object({
  full_name: z.string().min(2, "Tên tối thiểu 2 ký tự"),
  email: z.string().email("Email không hợp lệ"),
  password: z.string().min(8, "Mật khẩu tối thiểu 8 ký tự"),
  org_name: z.string().min(2, "Tên tổ chức tối thiểu 2 ký tự"),
});

type RegisterForm = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (values: RegisterForm) => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    try {
      const regRes = await fetch(`${apiBase}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: values.full_name,
          email: values.email,
          password: values.password,
          org_name: values.org_name,
        }),
      });
      const regJson = await regRes.json();

      if (!regRes.ok) {
        setError("root", { message: regJson?.detail ?? "Đăng ký thất bại. Email có thể đã tồn tại." });
        return;
      }

      // Auto-login sau khi đăng ký
      const loginRes = await fetch(`${apiBase}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: values.email, password: values.password }),
      });
      const loginJson = await loginRes.json();

      if (loginJson?.data?.access_token) {
        const token: string = loginJson.data.access_token;
        const payload = JSON.parse(atob(token.split(".")[1]));
        setAuth(token, {
          id: payload.sub,
          email: payload.email,
          full_name: payload.full_name,
          role: payload.role,
          org_id: payload.org_id,
        });
        router.push("/dashboard");
      }
    } catch {
      setError("root", { message: "Đã xảy ra lỗi. Vui lòng thử lại." });
    }
  };

  const inputClass =
    "w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-purple-500/50 focus:bg-white/10 focus:ring-2 focus:ring-purple-500/20";

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-purple-950 to-slate-900">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[600px] w-[600px] rounded-full bg-purple-500/10 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-[600px] w-[600px] rounded-full bg-indigo-500/10 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md px-4">
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-purple-500 to-indigo-600 shadow-lg shadow-purple-500/25">
            <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">HYLIST</h1>
          <p className="mt-1 text-sm text-slate-400">Tạo workspace của bạn</p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur-xl">
          <h2 className="mb-6 text-xl font-semibold text-white">Đăng ký</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Họ và tên</label>
              <input {...register("full_name")} placeholder="Nguyễn Văn A" className={inputClass} />
              {errors.full_name && <p className="mt-1.5 text-xs text-red-400">{errors.full_name.message}</p>}
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Email</label>
              <input {...register("email")} type="email" placeholder="you@company.com" className={inputClass} />
              {errors.email && <p className="mt-1.5 text-xs text-red-400">{errors.email.message}</p>}
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Mật khẩu</label>
              <input {...register("password")} type="password" placeholder="Tối thiểu 8 ký tự" className={inputClass} />
              {errors.password && <p className="mt-1.5 text-xs text-red-400">{errors.password.message}</p>}
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">Tên tổ chức</label>
              <input {...register("org_name")} placeholder="Acme Corp" className={inputClass} />
              {errors.org_name && <p className="mt-1.5 text-xs text-red-400">{errors.org_name.message}</p>}
            </div>

            {errors.root && (
              <div className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400 ring-1 ring-red-500/20">
                {errors.root.message}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-xl bg-gradient-to-r from-purple-500 to-indigo-600 py-3 text-sm font-semibold text-white shadow-lg shadow-purple-500/25 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Đang tạo tài khoản..." : "Tạo tài khoản"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Đã có tài khoản?{" "}
            <Link href="/login" className="font-medium text-purple-400 hover:text-purple-300">
              Đăng nhập
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
