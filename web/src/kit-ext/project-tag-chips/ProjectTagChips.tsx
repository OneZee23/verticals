/* A literal tag list whose project tags get stronger chrome, on the kit's KChip. */
import { computed } from '../../reactivity'
import { KChip } from '../../kit'
import { cx, fallthrough } from '../../bind'
import { tracked } from '../../tracked'
import { useSetup } from '../../setup'
import './projectTagChips.css'

interface Props {
  tags: string[]
  projectTags: string[]
}

export const ProjectTagChips = tracked(function ProjectTagChips(raw: Props & Record<string, unknown>) {
  const { tags, projectTags, ...attrs } = raw
  const s = useSetup({ tags, projectTags }, (props) => {
    const projectSet = computed(() => new Set(props.projectTags))
    return { projectSet }
  })
  if (!tags.length) return null
  const projectSet = s.projectSet.value
  return (
    <div {...fallthrough({ className: 'project-tag-chips', 'data-role': 'tag-chips' }, attrs)}>
      {tags.map((tag) => (
        <KChip
          key={tag}
          className={cx('project-tag-chip', { 'project-tag-chip--project': projectSet.has(tag) })}
          data-tag={tag}
          data-project={projectSet.has(tag) ? 'true' : 'false'}
          data-role={projectSet.has(tag) ? 'project-tag-chip' : 'tag-chip'}
        >{tag}</KChip>
      ))}
    </div>
  )
})
