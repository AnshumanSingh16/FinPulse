"use client";

import { Suspense } from "react";
import { CfoDesk } from "@/components/cfo/desk";

export default function DeskPage() {
  return (
    <Suspense>
      <CfoDesk />
    </Suspense>
  );
}
