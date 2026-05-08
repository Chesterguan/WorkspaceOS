import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PROJECT_ID_RE = /^\/projects\/([^/]+)/;

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  // /projects/[id]/...
  const projectMatch = pathname.match(PROJECT_ID_RE);
  if (projectMatch) {
    const projectId = projectMatch[1];

    // /projects/new — let it fall through (it's the create-project page)
    if (projectId === 'new') {
      return NextResponse.next();
    }

    const sub = pathname.slice(projectMatch[0].length); // e.g. '/chat', '/drafts/abc'

    // Routes that intentionally keep their old path for v1 (inspector links here)
    if (sub === '/narrative' || sub === '/sync' || sub === '/timeline') {
      return NextResponse.next();
    }

    let target: URL | null = null;

    if (sub === '' || sub === '/' || sub === '/overview') {
      target = new URL(`/bench?project=${projectId}`, req.url);
    } else if (sub === '/chat') {
      target = new URL(`/bench?project=${projectId}&surface=r&mode=cofounder`, req.url);
    } else if (sub.startsWith('/research/paper')) {
      // /research/paper takes precedence over /research
      target = new URL(`/bench?project=${projectId}&surface=p`, req.url);
    } else if (sub === '/research' || sub.startsWith('/research/')) {
      target = new URL(`/bench?project=${projectId}&surface=r&mode=research`, req.url);
    } else if (sub === '/drafts' || sub.startsWith('/drafts/')) {
      target = new URL(`/bench?project=${projectId}&surface=d`, req.url);
    } else if (sub === '/blog' || sub.startsWith('/blog/')) {
      target = new URL(`/bench?project=${projectId}&surface=d&platform=blog`, req.url);
    } else if (sub === '/posting') {
      target = new URL(`/bench?project=${projectId}&surface=d`, req.url);
    } else if (sub === '/files') {
      target = new URL(`/bench?project=${projectId}&overlay=files`, req.url);
    } else if (sub === '/memory') {
      target = new URL(`/bench?project=${projectId}&overlay=memory`, req.url);
    }

    if (target) {
      return NextResponse.redirect(target);
    }
  }

  // Non-project-scoped redirects
  if (pathname === '/projects' || pathname === '/projects/') {
    return NextResponse.redirect(new URL('/bench', req.url));
  }
  if (pathname === '/portfolio' || pathname === '/portfolio/') {
    return NextResponse.redirect(new URL('/bench?overlay=portfolio', req.url));
  }
  if (pathname === '/portfolio/paper') {
    return NextResponse.redirect(new URL('/bench?surface=p&scope=portfolio', req.url));
  }
  if (pathname === '/knowledge') {
    // Preserve any existing search params (e.g. ?project=...) so deep links work
    const tail = search ? `&${search.slice(1)}` : '';
    return NextResponse.redirect(new URL(`/bench?surface=k${tail}`, req.url));
  }
  if (pathname === '/worklog') {
    return NextResponse.redirect(new URL('/bench?surface=w', req.url));
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
