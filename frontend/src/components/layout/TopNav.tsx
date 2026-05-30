import { NavLink } from "react-router-dom";

export function TopNav() {
  return (
    <nav className="top-nav" aria-label="Main navigation">
      <NavLink
        className={({ isActive }) => `top-nav-item${isActive ? " active" : ""}`}
        to="/breadth"
      >
        <span className="top-nav-item-icon" aria-hidden="true" />
        <span>Breadth</span>
      </NavLink>
      <NavLink
        className={({ isActive }) => `top-nav-item${isActive ? " active" : ""}`}
        to="/strong"
        end
      >
        <span className="top-nav-item-icon" aria-hidden="true" />
        <span>Strong Industry</span>
      </NavLink>
    </nav>
  );
}
