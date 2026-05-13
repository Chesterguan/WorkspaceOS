import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PROJECT_ID_RE = /^\/projects\/([^/]+)/;

/**
 * Bench UI demo: aggressive proxy.
 *
 * Every old project-scoped route AND every portfolio route redirects to a
 * bench surface or overlay. The classic UI pages still exist on disk
 * (shared components like ChatWindow, KnowledgeGraph live there) but they
 * are never directly visited — the bench is the only user-visible surface.
 */
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Per-project routes
  const projectMatch = pathname.match(PROJECT_ID_RE);
  if (projectMatch) {
    const projectId = projectMatch[1];

    // Create-project page is the one carve-out — bench has its own modal
    // but a user typing /projects/new gets the classic form. Acceptable.
    if (projectId === 'new') {
      return NextResponse.next();
    }

    const sub = pathname.slice(projectMatch[0].length);

    if (sub === '' || sub === '/' || sub === '/overview') {
      return NextResponse.redirect(new URL(`/bench?project=${projectId}`, req.url));
    }
    if (sub === '/chat') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&surface=cofounder`, req.url),
      );
    }
    if (sub === '/research' || sub.startsWith('/research/paper')) {
      // Research page → research roundtable; paper editor → papers surface.
      if (sub.startsWith('/research/paper')) {
        return NextResponse.redirect(
          new URL(`/bench?project=${projectId}&surface=papers`, req.url),
        );
      }
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&surface=research`, req.url),
      );
    }
    if (sub === '/drafts' || sub.startsWith('/drafts/')) {
      return NextResponse.redirect(new URL(`/bench?project=${projectId}&surface=drafts`, req.url));
    }
    if (sub === '/blog' || sub.startsWith('/blog/')) {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&surface=drafts&platform=blog`, req.url),
      );
    }
    if (sub === '/posting') {
      return NextResponse.redirect(new URL(`/bench?project=${projectId}&surface=drafts`, req.url));
    }
    if (sub === '/files') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&overlay=files`, req.url),
      );
    }
    if (sub === '/memory') {
      return NextResponse.redirect(
        new URL(`/bench?project=${projectId}&overlay=memory`, req.url),
      );
    }
    if (sub === '/narrative' || sub === '/sync' || sub === '/timeline') {
      // No bench surface for these yet — send to project inspector
      return NextResponse.redirect(new URL(`/bench?project=${projectId}`, req.url));
    }
    return NextResponse.next();
  }

  if (pathname === '/projects' || pathname === '/projects/') {
    return NextResponse.redirect(new URL('/bench', req.url));
  }
  if (pathname === '/portfolio' || pathname === '/portfolio/') {
    return NextResponse.redirect(new URL('/bench?overlay=portfolio', req.url));
  }
  if (pathname === '/portfolio/paper') {
    return NextResponse.redirect(new URL('/bench?surface=papers&scope=portfolio', req.url));
  }
  if (pathname === '/knowledge') {
    const tail = req.nextUrl.search ? `&${req.nextUrl.search.slice(1)}` : '';
    return NextResponse.redirect(new URL(`/bench?surface=knowledge${tail}`, req.url));
  }
  if (pathname === '/worklog') {
    return NextResponse.redirect(new URL('/bench?surface=worklog', req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/projects',
    '/projects/:path*',
    '/portfolio',
    '/portfolio/:path*',
    '/knowledge',
    '/worklog',
  ],
};
