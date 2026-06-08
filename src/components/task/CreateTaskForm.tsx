"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowUp, Image as ImageIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { TravelCapabilityId } from "@/lib/travel/capabilities";
import type { ActiveCliId } from "@/lib/utils/cliOptions";

interface ModelOption {
  id: string;
  name: string;
}

interface AssistantOption {
  id: string;
  name: string;
}

interface RoleModule {
  id: string;
  name: string;
  description: string;
  capabilityId: TravelCapabilityId;
  inputPlaceholder: string;
}

interface UploadedImage {
  id: string;
  name: string;
  url: string;
  path: string;
  file?: File;
}

interface CreateTaskFormProps {
  prompt: string;
  onPromptChange: (value: string) => void;
  isCreating: boolean;
  onSubmit: () => void;
  uploadedImages: UploadedImage[];
  onImagesChange: (images: UploadedImage[]) => void;
  selectedAssistant: ActiveCliId;
  onAssistantChange: (id: string) => void;
  assistantOptions: AssistantOption[];
  isAssistantSelectable: (id: string) => boolean;
  selectedModel: string;
  onModelChange: (id: string) => void;
  modelOptions: ModelOption[];
  selectedRole: RoleModule;
  onRoleChange?: (id: TravelCapabilityId) => void;
}

function CreateTaskForm({
  prompt,
  onPromptChange,
  isCreating,
  onSubmit,
  uploadedImages,
  onImagesChange,
  selectedRole,
}: CreateTaskFormProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      setIsUploading(true);
      const filesArray = Array.from(files as ArrayLike<File>);
      const imagesToAdd = filesArray
        .filter((file) => file.type.startsWith("image/"))
        .map((file) => ({
          id: crypto.randomUUID(),
          name: file.name,
          url: URL.createObjectURL(file),
          path: "",
          file,
        }));

      if (imagesToAdd.length > 0) {
        onImagesChange([...uploadedImages, ...imagesToAdd]);
      }
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [uploadedImages, onImagesChange]
  );

  const removeImage = (id: string) => {
    onImagesChange(
      uploadedImages.filter((img) => {
        if (img.id === id && img.url) URL.revokeObjectURL(img.url);
        return img.id !== id;
      })
    );
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      onDragEnter={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setIsDragOver(false);
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
        if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
      }}
      className={cn(
        "relative w-full max-w-4xl rounded-lg border bg-card text-card-foreground shadow-sm transition-colors",
        isDragOver ? "border-primary bg-primary/5" : "border-border"
      )}
    >
      {/* Uploaded image previews */}
      {uploadedImages.length > 0 && (
        <div className="flex flex-wrap gap-2 px-5 pt-4">
          {uploadedImages.map((image, index) => (
            <div key={image.id} className="group relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={image.url}
                alt={image.name}
                className="h-16 w-16 rounded-lg border border-slate-200 object-cover"
              />
              <span className="absolute bottom-1 left-1 rounded bg-black/55 px-1 text-[10px] text-white">
                图 {index + 1}
              </span>
              <button
                type="button"
                onClick={() => removeImage(image.id)}
                className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs text-white opacity-0 transition-opacity hover:bg-red-600 group-hover:opacity-100"
                aria-label={`移除图片 ${image.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <Textarea
        value={prompt}
        onChange={(e) => onPromptChange(e.target.value)}
        placeholder={selectedRole.inputPlaceholder}
        disabled={isCreating}
        className="min-h-[128px] resize-none border-0 px-5 py-4 text-[16px] leading-6 shadow-none focus-visible:ring-0"
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
      />

      {/* Drag overlay */}
      {isDragOver && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-primary bg-primary/10">
          <div className="text-center text-primary">
            <ImageIcon className="mx-auto mb-2 h-6 w-6" />
            <p className="text-sm font-semibold">将图片拖到这里</p>
            <p className="mt-1 text-xs">支持 JPG、PNG、GIF、WEBP</p>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-t px-3 py-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="relative h-9 w-9"
          aria-label="上传图片"
          asChild
        >
          <label>
            <ImageIcon className="h-4 w-4" />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => e.target.files && handleFiles(e.target.files)}
              disabled={isUploading || isCreating}
              className="sr-only"
            />
          </label>
        </Button>

        <Badge variant="secondary" className="h-9 rounded-md px-3 text-sm text-primary">
          {selectedRole.name}
        </Badge>

        <Button
          type="submit"
          disabled={(!prompt.trim() && uploadedImages.length === 0) || isCreating}
          size="icon"
          className="ml-auto h-9 w-9"
          aria-label="提交任务"
        >
          {isCreating ? (
            <svg
              className="h-4 w-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          ) : (
            <ArrowUp className="h-5 w-5" />
          )}
        </Button>
      </div>
    </form>
  );
}

export { CreateTaskForm };
export type { CreateTaskFormProps, UploadedImage };
