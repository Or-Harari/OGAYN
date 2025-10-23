import React from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAuth } from '@/stores/auth'

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

  return (
    <form onSubmit={handleSubmit(async v => {
      await login(v.email, v.password)
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
