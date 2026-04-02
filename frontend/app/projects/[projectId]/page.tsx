import { redirect } from "next/navigation";

interface Props {
  params: Promise<{ projectId: string }>;
}

export default async function ProjectIndexPage({ params }: Props) {
  const { projectId } = await params;
  redirect(`/projects/${projectId}/overview`);
}
