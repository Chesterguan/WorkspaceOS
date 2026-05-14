'use client';

// Soft first-run redirect: brand-new users who haven't completed the
// wizard AND have zero projects get bumped to /onboarding. Returning
// users (or anyone who explicitly skipped via the wizard) stay on
// /bench.
//
// Two safety properties that took an iteration to get right:
//
// 1. We must read fresh data, not the SWR cache from before Apply.
//    `applyConfig()` mutates the /config/onboarding/me cache on
//    success — but we belt-and-braces wait for `isValidating: false`
//    here so even a stale subscriber gets a fresh check.
//
// 2. We must fire the redirect at most once per mount. The
//    `checked.current` ref guards against the useEffect firing on
//    each SWR revalidation cycle and flapping back and forth.

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { fetchOnboardingState, type OnboardingState } from './api';
import { useProjects } from '@/lib/hooks/useProjects';

export function useFirstRunRedirect() {
  const router = useRouter();
  const checked = useRef(false);

  const { data: onboarding, isValidating: onboardingValidating } =
    useSWR<OnboardingState>(
      '/config/onboarding/me',
      fetchOnboardingState,
      { revalidateOnFocus: false, shouldRetryOnError: false },
    );
  const { data: projects, isLoading: projectsLoading } = useProjects();

  useEffect(() => {
    if (checked.current) return;
    // Don't decide until both queries have settled. Otherwise a stale
    // cached value can trigger the redirect before the revalidation
    // arrives — which is the bug that caused the
    // wizard → bench → wizard loop after Apply.
    if (!onboarding || projects === undefined) return;
    if (onboardingValidating || projectsLoading) return;
    checked.current = true;

    if (!onboarding.tutorial_completed && projects.length === 0) {
      router.replace('/onboarding');
    }
  }, [onboarding, projects, router, onboardingValidating, projectsLoading]);
}
