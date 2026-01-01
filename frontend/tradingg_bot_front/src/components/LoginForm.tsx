import React from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '@/stores/auth'
import { useLocation, useNavigate } from 'react-router-dom'

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(4),
})

type LoginInput = z.infer<typeof schema>

export function LoginForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginInput>({
    resolver: zodResolver(schema),
  })
  const login = useAuth((s) => s.login)
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <form onSubmit={handleSubmit(async v => {
      await login(v.email, v.password)
      try {
        const params = new URLSearchParams(location.search)
        const next = params.get('next')
        navigate(next || '/', { replace: true })
      } catch {
        navigate('/', { replace: true })
      }
    })}>
      <div className="form-row">
        <label>Email</label>
        <input className="input" type="email" {...register('email')} />
        {errors.email && <small style={{color: 'crimson'}}>{errors.email.message}</small>}
      </div>
      <div className="form-row">
        <label>Password</label>
        <input className="input" type="password" {...register('password')} />
        {errors.password && <small style={{color: 'crimson'}}>{errors.password.message}</small>}
      </div>
      <button className="button" type="submit" disabled={isSubmitting}>Login</button>
    </form>
  )
}
