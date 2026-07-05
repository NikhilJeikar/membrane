import { Breadcrumb, BreadcrumbItem } from "@carbon/react";

type Props = {
  title: string;
  description?: string;
  breadcrumbs?: { label: string; href?: string }[];
};

export default function PageHeader({ title, description, breadcrumbs }: Props) {
  return (
    <header className="page-header">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumb noTrailingSlash className="page-header__breadcrumb">
          {breadcrumbs.map((crumb) => (
            <BreadcrumbItem key={crumb.label} href={crumb.href}>
              {crumb.label}
            </BreadcrumbItem>
          ))}
        </Breadcrumb>
      )}
      <h1 className="page-header__title">{title}</h1>
      {description && <p className="page-header__description">{description}</p>}
    </header>
  );
}
