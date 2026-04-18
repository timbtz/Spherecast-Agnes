import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export const useOpportunities = () =>
  useQuery({ queryKey: ['opportunities'], queryFn: () => api.getOpportunities(), staleTime: 30_000 })

export const useIngredients = (grade?: string) =>
  useQuery({ queryKey: ['ingredients', grade], queryFn: () => api.getIngredients(grade), staleTime: 30_000 })

export const useCompliance = () =>
  useQuery({ queryKey: ['compliance'], queryFn: () => api.getCompliance(), staleTime: 30_000 })

export const useProposals = () =>
  useQuery({ queryKey: ['proposals'], queryFn: () => api.getProposals(), staleTime: 30_000 })

export const useRuns = () =>
  useQuery({ queryKey: ['runs'], queryFn: () => api.getRuns(), staleTime: 5_000, refetchInterval: 10_000 })

export const usePipelines = () =>
  useQuery({ queryKey: ['pipelines'], queryFn: () => api.getPipelines(), staleTime: 60_000 })

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: () => api.getHealth(), refetchInterval: 30_000 })
