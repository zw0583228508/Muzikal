import { useState } from "react";
import { Link, useLocation } from "wouter";
import { useListProjects, useCreateProject, useDeleteProject, Project } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, Music2, Clock, Calendar, Activity, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { format } from "date-fns";

export default function Home() {
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const { data: projects, isLoading } = useListProjects();
  
  const createMutation = useCreateProject({
    mutation: {
      onSuccess: (data) => {
        queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
        setLocation(`/project/${data.id}`);
      }
    }
  });

  const deleteMutation = useDeleteProject({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      }
    }
  });

  const handleCreate = () => {
    const name = prompt("Project Name:", "New Track");
    if (!name) return;
    createMutation.mutate({ data: { name, description: "A new masterpiece" } });
  };

  const getStatusColor = (status: Project['status']) => {
    switch(status) {
      case 'done': return 'default';
      case 'error': return 'destructive';
      case 'analyzing':
      case 'arranging':
      case 'exporting': return 'accent';
      default: return 'outline';
    }
  };

  return (
    <div className="min-h-screen bg-background relative overflow-y-auto">
      {/* Background image & gradient */}
      <div className="absolute inset-0 z-0">
        <img 
          src={`${import.meta.env.BASE_URL}images/studio-bg.png`} 
          alt="Studio Background" 
          className="w-full h-full object-cover opacity-20 object-center"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/80 via-background to-background" />
      </div>

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/20 to-accent/20 p-0.5 shadow-[0_0_30px_rgba(0,240,255,0.1)]">
              <div className="w-full h-full bg-card rounded-[15px] flex items-center justify-center backdrop-blur-xl">
                <img src={`${import.meta.env.BASE_URL}images/logo-icon.png`} alt="Logo" className="w-8 h-8 opacity-80" />
              </div>
            </div>
            <div>
              <h1 className="text-3xl md:text-5xl font-display font-bold text-white text-glow">MusicAI Studio</h1>
              <p className="text-muted-foreground mt-1">Intelligence & Generation DAW</p>
            </div>
          </div>
          <Button size="lg" onClick={handleCreate} disabled={createMutation.isPending} className="group">
            {createMutation.isPending ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <Plus className="mr-2 h-5 w-5 group-hover:scale-125 transition-transform" />}
            New Project
          </Button>
        </header>

        {isLoading ? (
          <div className="flex justify-center items-center py-32">
            <Loader2 className="w-10 h-10 text-primary animate-spin" />
          </div>
        ) : !projects || projects.length === 0 ? (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} 
            animate={{ opacity: 1, scale: 1 }}
            className="daw-panel p-12 text-center max-w-2xl mx-auto border-dashed border-white/20"
          >
            <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-6">
              <Music2 className="w-10 h-10 text-primary" />
            </div>
            <h2 className="text-2xl font-display font-bold mb-4">No Projects Yet</h2>
            <p className="text-muted-foreground mb-8">Start your journey by creating a new project. You can upload audio for analysis, or start generating from scratch.</p>
            <Button size="lg" variant="glow" onClick={handleCreate}>Create Your First Project</Button>
          </motion.div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project, i) => (
              <motion.div
                key={project.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <div className="daw-panel group cursor-pointer hover:border-primary/50 transition-colors h-full flex flex-col">
                  <Link href={`/project/${project.id}`} className="p-6 flex-1 block">
                    <div className="flex justify-between items-start mb-4">
                      <h3 className="text-xl font-bold text-white group-hover:text-primary transition-colors">{project.name}</h3>
                      <Badge variant={getStatusColor(project.status)} className="capitalize">
                        {project.status === 'done' ? 'Ready' : project.status}
                      </Badge>
                    </div>
                    
                    <div className="space-y-3 mb-6">
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Clock className="w-4 h-4 mr-2" />
                        {project.audioDurationSeconds ? `${Math.round(project.audioDurationSeconds)}s` : 'No audio'}
                      </div>
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Activity className="w-4 h-4 mr-2" />
                        {project.audioFileName || 'Empty timeline'}
                      </div>
                      <div className="flex items-center text-sm text-muted-foreground">
                        <Calendar className="w-4 h-4 mr-2" />
                        {format(new Date(project.createdAt), 'MMM d, yyyy')}
                      </div>
                    </div>
                  </Link>
                  
                  <div className="px-6 py-4 border-t border-white/5 flex justify-between items-center bg-black/20">
                    <Button variant="ghost" size="sm" asChild>
                      <Link href={`/project/${project.id}`} className="text-primary hover:text-primary/80">Open Studio</Link>
                    </Button>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm('Delete project?')) {
                          deleteMutation.mutate({ projectId: project.id });
                        }
                      }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
