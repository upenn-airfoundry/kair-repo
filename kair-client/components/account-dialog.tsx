'use client';

import React, { useState, useEffect } from "react";
import { Dialog, DialogTitle, DialogContent, DialogActions } from "@mui/material";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { useAuth } from '@/context/auth-context';
import { config } from '@/config';
import { useSecureFetch } from '@/hooks/useSecureFetch';

interface AccountDialogProps {
  open: boolean;
  onClose: () => void;
}

type Project = {
  id: string;
  name: string;
  // add other fields if needed
};

export default function AccountDialog({ open, onClose }: AccountDialogProps) {
  const { user } = useAuth();
  const [profile, setProfile] = useState({
    fullName: user?.name || "",
    biosketch: user?.profile?.biosketch || "",
    expertise: user?.profile?.expertise || "",
    projects: user?.profile?.projects || "",
    publications: user?.profile?.publications || [],
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState("");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");

  useEffect(() => {
    if (open) {
      const fetchProjects = async () => {
        try {
          const response = await secureFetch(`${config.apiBaseUrl}/api/projects/list?search=${search}`);
          if (response.ok) {
            const data = await response.json();
            setProjects(data.projects || []);
          }    
        } catch (error) {
          console.error("Error fetching projects:", error);
        }
      };
      fetchProjects();
    }
  }, [open, search]);

  const handleSave = async () => {
    await fetch(`${config.apiBaseUrl}/api/account/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: 'include',
      body: JSON.stringify({ profile }),
    });
    onClose();
  };

  const handleCreateProject = async () => {
    const res = await fetch(`${config.apiBaseUrl}/api/projects/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: 'include',
      body: JSON.stringify({ name: newProjectName, description: newProjectDesc }),
    });
    const data = await res.json();
    if (data.project_id) {
      setSelectedProject(data.project_id);
      setNewProjectName("");
      setNewProjectDesc("");
      setSearch("");
          }
  };

  // Publication fields: title, authors, venue, year, url, doi, abstract
  const handlePublicationChange = (idx: number, field: string, value: string) => {
    const pubs = [...profile.publications];
    pubs[idx][field] = value;
    setProfile({ ...profile, publications: pubs });
  };

  const handleAddPublication = () => {
    setProfile({
      ...profile,
      publications: [
        ...profile.publications,
        { title: "", authors: "", venue: "", year: "", url: "", doi: "", abstract: "" }
      ]
    });
  };

  const handleRemovePublication = (idx: number) => {
    const pubs = [...profile.publications];
    pubs.splice(idx, 1);
    setProfile({ ...profile, publications: pubs });
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Edit Account</DialogTitle>
      <DialogContent>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="fullName" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Full Name
          </label>
          <Input
            id="fullName"
            value={profile.fullName}
            onChange={e => setProfile({ ...profile, fullName: e.target.value })}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="biosketch" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Biosketch
          </label>
          <textarea
            id="biosketch"
            value={profile.biosketch}
            onChange={e => setProfile({ ...profile, biosketch: e.target.value })}
            rows={4}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="expertise" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Expertise
          </label>
          <textarea
            id="expertise"
            value={profile.expertise}
            onChange={e => setProfile({ ...profile, expertise: e.target.value })}
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="projects" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Projects
          </label>
          <textarea
            id="projects"
            value={profile.projects}
            onChange={e => setProfile({ ...profile, projects: e.target.value })}
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Publications
          </label>
          <table style={{ width: "100%", marginBottom: 8, borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ fontWeight: "bold" }}>Title</th>
                <th style={{ fontWeight: "bold" }}>Authors</th>
                <th style={{ fontWeight: "bold" }}>Venue</th>
                <th style={{ fontWeight: "bold" }}>Year</th>
                <th style={{ fontWeight: "bold" }}>URL</th>
                <th style={{ fontWeight: "bold" }}>DOI</th>
                <th style={{ fontWeight: "bold" }}>Abstract</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {profile.publications.map((pub, idx) => (
                <tr key={idx}>
                  <td>
                    <Input
                      value={pub.title}
                      onChange={e => handlePublicationChange(idx, "title", e.target.value)}
                      placeholder="Title"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.authors}
                      onChange={e => handlePublicationChange(idx, "authors", e.target.value)}
                      placeholder="Authors"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.venue}
                      onChange={e => handlePublicationChange(idx, "venue", e.target.value)}
                      placeholder="Venue"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.year}
                      onChange={e => handlePublicationChange(idx, "year", e.target.value)}
                      placeholder="Year"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.url}
                      onChange={e => handlePublicationChange(idx, "url", e.target.value)}
                      placeholder="URL"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.doi}
                      onChange={e => handlePublicationChange(idx, "doi", e.target.value)}
                      placeholder="DOI"
                    />
                  </td>
                  <td>
                    <Input
                      value={pub.abstract}
                      onChange={e => handlePublicationChange(idx, "abstract", e.target.value)}
                      placeholder="Abstract"
                    />
                  </td>
                  <td>
                    <Button variant="outline" onClick={() => handleRemovePublication(idx)}>Remove</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Button onClick={handleAddPublication}>Add Publication</Button>
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="searchProjects" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            Search Projects
          </label>
          <Input
            id="searchProjects"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <ul>
            {projects.map(proj => (
              <li key={proj.id}>
                <Button
                  variant={selectedProject === proj.id ? "default" : "outline"}
                  onClick={() => setSelectedProject(proj.id)}
                >
                  {proj.name}
                </Button>
              </li>
            ))}
          </ul>
        </div>
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="newProjectName" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            New Project Name
          </label>
          <Input
            id="newProjectName"
            value={newProjectName}
            onChange={e => setNewProjectName(e.target.value)}
          />
          <label htmlFor="newProjectDesc" style={{ fontWeight: "bold", display: "block", marginBottom: 4 }}>
            New Project Description
          </label>
          <Input
            id="newProjectDesc"
            value={newProjectDesc}
            onChange={e => setNewProjectDesc(e.target.value)}
          />
          <Button onClick={handleCreateProject}>Create Project</Button>
        </div>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleSave}>Save</Button>
        <Button onClick={onClose}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}